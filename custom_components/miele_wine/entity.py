"""Shared base entity: wires coordinator + device info."""

from __future__ import annotations

from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MieleWineCoordinator


class MieleWineEntity(CoordinatorEntity[MieleWineCoordinator]):
    """Base entity with device info from the appliance's Ident."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MieleWineCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        label = self.coordinator.ident.get("DeviceIdentLabel", {}) if self.coordinator.ident else {}
        model = label.get("TechType") or "Wine conditioning unit"
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.mac)},
            manufacturer="Miele",
            model=model,
            name="Miele wine cabinet",
            serial_number=self.coordinator.mac,
        )
