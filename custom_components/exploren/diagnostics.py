"""Diagnostics for the Exploren integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ExplorenCoordinator

REDACT = {
    "access_token",
    "refresh_token",
    "token",
    "email",
    "username",
    "paymentMethodId",
    "identifier",
    "name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: ExplorenCoordinator = hass.data[DOMAIN][entry.entry_id]
    websocket = getattr(coordinator, "websocket", None)
    return {
        "entry_data": async_redact_data(dict(entry.data), REDACT),
        "raw": async_redact_data(coordinator.raw, REDACT),
        "normalized": async_redact_data(coordinator.data or {}, REDACT),
        "websocket": websocket.status if websocket is not None else None,
    }
