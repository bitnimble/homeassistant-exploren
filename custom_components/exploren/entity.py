"""Base entity for the Exploren integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ExplorenCoordinator


class ExplorenEvseEntity(CoordinatorEntity[ExplorenCoordinator]):
    """Base entity bound to a single EVSE (connector)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ExplorenCoordinator, evse_id: str) -> None:
        super().__init__(coordinator)
        self._evse_id = evse_id

    @property
    def evse(self) -> dict[str, Any]:
        return self.coordinator.data["evses"].get(self._evse_id, {})

    @property
    def session(self) -> dict[str, Any] | None:
        """The active session, only if it belongs to this EVSE."""
        session = self.coordinator.data.get("session")
        if session and str(session.get("evseId")) == self._evse_id:
            return session
        return None

    @property
    def available(self) -> bool:
        return super().available and self._evse_id in self.coordinator.data["evses"]

    @property
    def device_info(self) -> DeviceInfo:
        charge_point = self.evse.get("chargePoint", {})
        name = (
            charge_point.get("name")
            or self.evse.get("identifier")
            or f"EVSE {self._evse_id}"
        )
        return DeviceInfo(
            identifiers={(DOMAIN, self._evse_id)},
            name=name,
            manufacturer="Exploren",
            model=charge_point.get("model") or "AMPECO charge point",
        )
