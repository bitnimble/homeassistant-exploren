"""Async client for the Exploren (AMPECO) app API.

Auth is AMPECO-native Laravel Passport: a password grant against
`/app/oauth/token` returns an access+refresh pair. Passport rotates tokens on
refresh (old pair revoked, new pair issued), so the whole bundle is persisted
after every refresh via the `on_token_update` callback.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .const import APP_ID, APP_VERSION, BASE_URL, CLIENT_ID, CLIENT_SECRET

TokenUpdate = Callable[[dict[str, Any]], Awaitable[None]]

# Refresh this many seconds before the access token actually expires.
_EXPIRY_SKEW = 60


class ExplorenError(Exception):
    """A request to the Exploren API failed."""


class ExplorenAuthError(ExplorenError):
    """Authentication failed (bad credentials or dead refresh token)."""


class ExplorenApi:
    """Minimal async client covering auth, chargers and sessions."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        email: str | None = None,
        password: str | None = None,
        token: dict[str, Any] | None = None,
        on_token_update: TokenUpdate | None = None,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: dict[str, Any] = token or {}
        self._on_token_update = on_token_update

    @property
    def token(self) -> dict[str, Any]:
        return self._token

    # -- auth ---------------------------------------------------------------

    def _base_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": "en",
            "X-App-Id": APP_ID,
            "X-App-Version": APP_VERSION,
            "User-Agent": f"Exploren/{APP_VERSION} (HomeAssistant)",
        }

    async def _oauth(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            **payload,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "*",
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/app/oauth/token",
                json=body,
                headers=self._base_headers(),
            ) as resp:
                data = await self._read(resp)
                status = resp.status
        except aiohttp.ClientError as err:
            raise ExplorenError(f"Connection error: {err}") from err

        if status == 200 and isinstance(data, dict) and data.get("access_token"):
            data["expires_at"] = time.time() + float(data.get("expires_in", 0))
            self._token = data
            if self._on_token_update is not None:
                await self._on_token_update(data)
            return data
        raise ExplorenAuthError(f"OAuth failed ({status}): {data}")

    async def login(self) -> dict[str, Any]:
        if not self._email or not self._password:
            raise ExplorenAuthError("No credentials available for login")
        return await self._oauth(
            {
                "grant_type": "password",
                "username": self._email,
                "password": self._password,
            }
        )

    async def _refresh(self) -> dict[str, Any]:
        refresh_token = self._token.get("refresh_token")
        if not refresh_token:
            return await self.login()
        try:
            return await self._oauth(
                {"grant_type": "refresh_token", "refresh_token": refresh_token}
            )
        except ExplorenAuthError:
            # Refresh token expired/revoked: fall back to a full login.
            if self._email and self._password:
                return await self.login()
            raise

    async def _valid_token(self) -> str:
        expires_at = self._token.get("expires_at")
        if not self._token.get("access_token") or (
            expires_at is not None and time.time() >= expires_at - _EXPIRY_SKEW
        ):
            await self._refresh()
        return self._token["access_token"]

    # -- requests -----------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        retry: bool = True,
        allow_not_found: bool = False,
    ) -> Any:
        token = await self._valid_token()
        headers = {**self._base_headers(), "Authorization": f"Bearer {token}"}
        try:
            async with self._session.request(
                method, f"{BASE_URL}{path}", json=json_body, headers=headers
            ) as resp:
                if resp.status == 401 and retry:
                    await self._refresh()
                    return await self._request(
                        method,
                        path,
                        json_body=json_body,
                        retry=False,
                        allow_not_found=allow_not_found,
                    )
                data = await self._read(resp)
                status = resp.status
        except aiohttp.ClientError as err:
            raise ExplorenError(f"Connection error: {err}") from err

        # Some endpoints (e.g. session/active) 404 to mean "nothing here".
        if status == 404 and allow_not_found:
            return None
        if status == 401:
            raise ExplorenAuthError(f"{method} {path} -> 401: {data}")
        if status >= 400:
            raise ExplorenError(f"{method} {path} -> {status}: {data}")
        return data

    @staticmethod
    async def _read(resp: aiohttp.ClientResponse) -> Any:
        text = await resp.text()
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return text

    # -- endpoints ----------------------------------------------------------

    async def get_charge_points(self) -> Any:
        # Each EVSE embeds its active `session` (if any), so this is the only
        # call the coordinator needs.
        return await self._request("GET", "/app/personal/charge-points")

    async def get_settings_global(self) -> Any:
        # Carries the broadcast config: broadcast.url + broadcast.channelPrefix.
        return await self._request("GET", "/app/settings/global")

    async def get_profile(self) -> Any:
        return await self._request("GET", "/app/profile")

    async def valid_access_token(self) -> str:
        """A current access token (refreshed if needed) for the websocket."""
        return await self._valid_token()

    async def start_session(self, evse_identifier: int | str) -> Any:
        # `evseId` is the EVSE's public identifier (e.g. "3692"), not its
        # internal id. Sent numeric when it looks numeric, else as-is.
        value: int | str = (
            int(evse_identifier)
            if str(evse_identifier).isdigit()
            else evse_identifier
        )
        return await self._request(
            "POST",
            "/app/session/start",
            json_body={"evseId": value, "source": "App"},
        )

    async def stop_session(self, session_id: int | str) -> Any:
        # 404 means the session already ended: a no-op for a stop action.
        return await self._request(
            "POST", f"/app/session/{session_id}/stop", allow_not_found=True
        )
