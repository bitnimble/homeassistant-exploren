"""Data coordinator for the Exploren integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ExplorenApi, ExplorenAuthError, ExplorenError
from .const import ACTIVE_SCAN_INTERVAL, IDLE_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def find_key(obj: Any, key: str) -> Any:
    """First non-null occurrence of `key` anywhere in nested json."""
    if isinstance(obj, dict):
        if obj.get(key) is not None:
            return obj[key]
        for value in obj.values():
            found = find_key(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_key(value, key)
            if found is not None:
                return found
    return None


class ExplorenCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /app/personal/charge-points (which embeds the active session)."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: ExplorenApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=IDLE_SCAN_INTERVAL),
        )
        self.entry = entry
        self.api = api
        # Kept for diagnostics.
        self.raw: dict[str, Any] = {}
        # Set by __init__.py after setup; stopped on unload.
        self.websocket: Any = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            charge_points = await self.api.get_charge_points()
        except ExplorenAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ExplorenError as err:
            raise UpdateFailed(str(err)) from err

        self.raw = {"charge_points": charge_points}
        data = _normalize(charge_points)

        # Poll faster while any connector has an active session.
        charging = any(evse.get("session") for evse in data["evses"].values())
        self.update_interval = timedelta(
            seconds=ACTIVE_SCAN_INTERVAL if charging else IDLE_SCAN_INTERVAL
        )

        _LOGGER.debug(
            "update: evse ids=%s, charging=%s, states=%s",
            list(data["evses"]),
            charging,
            {k: v.get("status") for k, v in data["evses"].items()},
        )
        return data


def _normalize(charge_points: Any) -> dict[str, Any]:
    """Flatten into {evses: {id: evse}}; each evse keeps its embedded session."""
    if isinstance(charge_points, dict):
        charge_points = charge_points.get("data", charge_points.get("chargePoints", []))
    if not isinstance(charge_points, list):
        charge_points = []

    evses: dict[str, dict[str, Any]] = {}
    for cp in charge_points:
        if not isinstance(cp, dict):
            continue
        for evse in cp.get("evses", []) or []:
            if not isinstance(evse, dict) or evse.get("id") is None:
                continue
            evses[str(evse["id"])] = {**evse, "chargePoint": cp}

    return {"evses": evses}
