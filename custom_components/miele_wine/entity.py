"""Shared base entity: wires coordinator + device info."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MieleWineCoordinator
from .ident import device_ident


class MieleWineEntity(CoordinatorEntity[MieleWineCoordinator]):
    """Base entity with device info from the appliance's Ident."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MieleWineCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        # identifiers and name are deliberately unchanged: both key the device
        # registry entry, and touching either would orphan the existing device
        # and every entity under it.
        info = device_ident(self.coordinator.ident, self.coordinator.mac)
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.mac)},
            manufacturer=info.manufacturer,
            model=info.model,
            name="Miele wine cabinet",
            serial_number=info.serial,
            sw_version=info.sw_version,
            hw_version=info.hw_version,
        )
