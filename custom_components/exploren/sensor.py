"""Sensor platform for the Exploren integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ExplorenCoordinator
from .entity import ExplorenEvseEntity


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _energy_kwh(session: dict[str, Any] | None) -> float | None:
    if not session:
        return None
    wh = _num(session.get("energy"))
    return wh / 1000 if wh is not None else None


@dataclass(frozen=True, kw_only=True)
class ExplorenSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    # (evse, session_or_none, soc) -> state
    value_fn: Callable[[dict[str, Any], dict[str, Any] | None, Any], Any]


SENSORS: tuple[ExplorenSensorDescription, ...] = (
    ExplorenSensorDescription(
        key="evse_status",
        translation_key="evse_status",
        icon="mdi:ev-station",
        value_fn=lambda evse, session, soc: evse.get("status") or evse.get("evseStatus"),
    ),
    ExplorenSensorDescription(
        key="charging_state",
        translation_key="charging_state",
        icon="mdi:state-machine",
        value_fn=lambda evse, session, soc: (
            session.get("chargingState") if session else "idle"
        ),
    ),
    ExplorenSensorDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        # API reports Wh; convert to kWh.
        value_fn=lambda evse, session, soc: _energy_kwh(session),
    ),
    ExplorenSensorDescription(
        key="session_power",
        translation_key="session_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda evse, session, soc: _num(session.get("power")) if session else None,
    ),
    ExplorenSensorDescription(
        key="session_duration",
        translation_key="session_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda evse, session, soc: _num(session.get("duration")) if session else None,
    ),
    ExplorenSensorDescription(
        key="session_cost",
        translation_key="session_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        value_fn=lambda evse, session, soc: _num(session.get("amount")) if session else None,
    ),
    ExplorenSensorDescription(
        key="vehicle_soc",
        translation_key="vehicle_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda evse, session, soc: _num(soc),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ExplorenCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        ExplorenSensor(coordinator, evse_id, description)
        for evse_id in coordinator.data["evses"]
        for description in SENSORS
    ]
    async_add_entities(entities)


class ExplorenSensor(ExplorenEvseEntity, SensorEntity):
    """A single Exploren sensor."""

    entity_description: ExplorenSensorDescription

    def __init__(
        self,
        coordinator: ExplorenCoordinator,
        evse_id: str,
        description: ExplorenSensorDescription,
    ) -> None:
        super().__init__(coordinator, evse_id)
        self.entity_description = description
        self._attr_unique_id = f"{evse_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.evse, self.session, self.coordinator.data.get("soc"))

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.key == "session_cost":
            session = self.session or {}
            currency = session.get("currency") or {}
            return currency.get("code") or None
        return self.entity_description.native_unit_of_measurement
