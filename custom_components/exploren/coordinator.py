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
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

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
    """Polls charge points and the active session."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: ExplorenApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            charge_points = await self.api.get_charge_points()
            active = await self.api.get_active_session()
        except ExplorenAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ExplorenError as err:
            raise UpdateFailed(str(err)) from err
        return _normalize(charge_points, active)


def _normalize(charge_points: Any, active: Any) -> dict[str, Any]:
    """Flatten the responses into {evses: {id: evse}, session, soc}."""
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

    # The active-session payload wraps the session under "session"; when the
    # response *is* the session it has an id and no nested "session".
    session = find_key(active, "session") if active else None
    if session is None and isinstance(active, dict) and active.get("id"):
        session = active

    soc = find_key(active, "carBatteryPercent")

    return {"evses": evses, "session": session, "soc": soc}
