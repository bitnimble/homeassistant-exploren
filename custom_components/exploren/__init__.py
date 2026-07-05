"""The Exploren EV Charging integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ExplorenApi
from .const import CONF_TOKEN, DOMAIN
from .coordinator import ExplorenCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Exploren from a config entry."""
    session = async_get_clientsession(hass)

    async def _save_token(token: dict[str, Any]) -> None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_TOKEN: token}
        )

    api = ExplorenApi(
        session,
        email=entry.data.get(CONF_EMAIL),
        password=entry.data.get(CONF_PASSWORD),
        token=entry.data.get(CONF_TOKEN),
        on_token_update=_save_token,
    )

    coordinator = ExplorenCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
