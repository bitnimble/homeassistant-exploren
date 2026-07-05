"""Button platform for the Exploren integration: start/stop charging."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ExplorenError
from .const import DOMAIN
from .coordinator import ExplorenCoordinator
from .entity import ExplorenEvseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ExplorenCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []
    for evse_id in coordinator.data["evses"]:
        entities.append(ExplorenStartButton(coordinator, evse_id))
        entities.append(ExplorenStopButton(coordinator, evse_id))
    async_add_entities(entities)


class ExplorenStartButton(ExplorenEvseEntity, ButtonEntity):
    """Starts a charging session on this connector ('Tap to confirm charge')."""

    _attr_translation_key = "start_charging"
    _attr_icon = "mdi:play"

    def __init__(self, coordinator: ExplorenCoordinator, evse_id: str) -> None:
        super().__init__(coordinator, evse_id)
        self._attr_unique_id = f"{evse_id}_start_charging"

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.start_session(self._evse_id)
        except ExplorenError as err:
            raise HomeAssistantError(f"Failed to start charging: {err}") from err
        await self.coordinator.async_request_refresh()


class ExplorenStopButton(ExplorenEvseEntity, ButtonEntity):
    """Stops the active charging session on this connector."""

    _attr_translation_key = "stop_charging"
    _attr_icon = "mdi:stop"

    def __init__(self, coordinator: ExplorenCoordinator, evse_id: str) -> None:
        super().__init__(coordinator, evse_id)
        self._attr_unique_id = f"{evse_id}_stop_charging"

    async def async_press(self) -> None:
        session = self.session
        if not session or session.get("id") is None:
            raise HomeAssistantError("No active session to stop on this connector")
        try:
            await self.coordinator.api.stop_session(session["id"])
        except ExplorenError as err:
            raise HomeAssistantError(f"Failed to stop charging: {err}") from err
        await self.coordinator.async_request_refresh()
