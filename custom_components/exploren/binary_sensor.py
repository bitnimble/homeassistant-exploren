"""Binary sensor platform for the Exploren integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ExplorenCoordinator
from .entity import ExplorenEvseEntity

_CHARGING_STATES = {"charging"}
_CONNECTED_STATES = {"charging", "preparing", "suspendedev", "suspendedevse", "finishing"}


def _evse_state(evse: dict[str, Any], session: dict[str, Any] | None) -> str:
    state = evse.get("status") or evse.get("evseStatus") or ""
    if session:
        state = session.get("evseStatus") or session.get("chargingState") or state
    return str(state).lower()


@dataclass(frozen=True, kw_only=True)
class ExplorenBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any], dict[str, Any] | None], bool]


BINARY_SENSORS: tuple[ExplorenBinaryDescription, ...] = (
    ExplorenBinaryDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda evse, session: _evse_state(evse, session) in _CHARGING_STATES,
    ),
    ExplorenBinaryDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda evse, session: session is not None
        or _evse_state(evse, session) in _CONNECTED_STATES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ExplorenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ExplorenBinarySensor(coordinator, evse_id, description)
        for evse_id in coordinator.data["evses"]
        for description in BINARY_SENSORS
    )


class ExplorenBinarySensor(ExplorenEvseEntity, BinarySensorEntity):
    entity_description: ExplorenBinaryDescription

    def __init__(
        self,
        coordinator: ExplorenCoordinator,
        evse_id: str,
        description: ExplorenBinaryDescription,
    ) -> None:
        super().__init__(coordinator, evse_id)
        self.entity_description = description
        self._attr_unique_id = f"{evse_id}_{description.key}"

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.evse, self.session)
