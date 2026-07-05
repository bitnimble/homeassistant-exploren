"""Real-time updates over the AMPECO `laravel-echo-server` websocket.

The echo host runs socket.io v2 (Engine.IO v3), not Pusher. Config is discovered
from /app/settings/global (broadcast.url + broadcast.channelPrefix) and the user
id from /app/profile. We subscribe to the private user channel and refresh the
coordinator on any broadcast event (SessionChanged, EVSEChargingPercentageChanged,
PersonalEVSEStatusChange, ...).

Channel auth: the subscribe frame carries `auth.headers` = Authorization (bearer)
+ X-Endpoint (the API base URL). The shared echo server uses X-Endpoint to route
its server-side /broadcasting/auth call to this tenant.

Additive: on any failure the integration falls back to REST polling.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any
from urllib.parse import urlparse

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ExplorenApi
from .const import BASE_URL, BROADCAST_CHANNEL_PREFIX, BROADCAST_ENDPOINT
from .coordinator import find_key

_LOGGER = logging.getLogger(__name__)

_MAX_BACKOFF = 60
_REFRESH_DEBOUNCE = 2.0
_PING_INTERVAL = 20  # send an Engine.IO ping if idle this long


class ExplorenWebsocket:
    """Manages the socket.io connection lifecycle."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ExplorenApi,
        on_event: Callable[[], Awaitable[None]],
    ) -> None:
        self._hass = hass
        self._api = api
        self._on_event = on_event
        self._task: asyncio.Task | None = None
        self._closing = False
        self._config: dict[str, Any] | None = None
        self._last_refresh = float("-inf")
        # Observable status for diagnostics.
        self.subscribed = False
        self.last_error: str | None = None
        self.event_count = 0

    @property
    def status(self) -> dict[str, Any]:
        cfg = self._config or {}
        return {
            "discovered": self._config is not None,
            "host": cfg.get("host"),
            "channel": cfg.get("channel"),
            "subscribed": self.subscribed,
            "events_received": self.event_count,
            "last_error": self.last_error,
        }

    async def async_start(self) -> None:
        self._closing = False
        self._task = self._hass.async_create_background_task(
            self._run(), "exploren-websocket"
        )

    async def async_stop(self) -> None:
        self._closing = True
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _discover(self) -> dict[str, Any] | None:
        settings = await self._api.get_settings_global()
        profile = await self._api.get_profile()

        broadcast = find_key(settings, "broadcast") or {}
        prefix = broadcast.get("channelPrefix") or BROADCAST_CHANNEL_PREFIX
        url = broadcast.get("url") or BROADCAST_ENDPOINT
        user_id = (profile or {}).get("id") or find_key(profile, "id")
        host = urlparse(url).hostname
        if not user_id or not host:
            _LOGGER.warning("websocket disabled: missing user id or host")
            return None

        config = {
            "host": host,
            "channel": f"private-{prefix}.user.{user_id}",
        }
        _LOGGER.debug("websocket config: %s", config)
        return config

    async def _run(self) -> None:
        backoff = 1
        while not self._closing:
            try:
                if self._config is None:
                    self._config = await self._discover()
                if self._config is None:
                    return
                await self._connect_and_listen(self._config)
                backoff = 1
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - never let the task die
                self.last_error = f"{type(err).__name__}: {err}"
                _LOGGER.debug("websocket error, will reconnect: %s", err)
            if self._closing:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)

    async def _connect_and_listen(self, config: dict[str, Any]) -> None:
        token = await self._api.valid_access_token()
        url = f"wss://{config['host']}/socket.io/?EIO=3&transport=websocket"
        subscribe = "42" + json.dumps(
            [
                "subscribe",
                {
                    "channel": config["channel"],
                    "auth": {
                        "headers": {
                            "Authorization": f"Bearer {token}",
                            "X-Endpoint": BASE_URL,
                        }
                    },
                },
            ]
        )
        session = async_get_clientsession(self._hass)
        self.subscribed = False
        _LOGGER.debug("websocket connecting to %s", config["host"])
        async with session.ws_connect(url, heartbeat=None) as ws:
            while not self._closing:
                try:
                    msg = await ws.receive(timeout=_PING_INTERVAL)
                except asyncio.TimeoutError:
                    await ws.send_str("2")  # Engine.IO client ping
                    continue
                if msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                await self._handle(ws, msg.data, subscribe)

    async def _handle(
        self, ws: aiohttp.ClientWebSocketResponse, data: str, subscribe: str
    ) -> None:
        # Engine.IO: 0=open, 2=ping, 3=pong, 4=message. Socket.IO (in a 4
        # message): 40=connect, 42=event.
        if data == "2":
            await ws.send_str("3")  # reply to server ping
        elif data.startswith("40"):
            await ws.send_str(subscribe)
            self.subscribed = True
        elif data.startswith("42"):
            await self._on_socketio_event(data[2:])

    async def _on_socketio_event(self, payload: str) -> None:
        try:
            frame = json.loads(payload)
        except ValueError:
            return
        if not isinstance(frame, list) or not frame:
            return
        event = frame[0]
        if event == "subscription_error":
            # frame = ["subscription_error", channel, code]; keep the code, drop
            # the channel (it embeds the user id) so it can't leak via status.
            self.subscribed = False
            self.last_error = f"subscription_error (code {frame[-1]})"
            _LOGGER.warning("websocket %s", self.last_error)
            return
        self.event_count += 1
        _LOGGER.debug("websocket event %s", event)
        await self._trigger_refresh()

    async def _trigger_refresh(self) -> None:
        now = self._hass.loop.time()
        if now - self._last_refresh < _REFRESH_DEBOUNCE:
            return
        self._last_refresh = now
        await self._on_event()
