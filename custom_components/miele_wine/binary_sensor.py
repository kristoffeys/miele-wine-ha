"""Per-zone door binary sensors (Door.Value: 1=open, 2=closed)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import MieleWineEntity

DOOR_OPEN = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        ZoneDoorSensor(coordinator, z)
        for z in sorted(coordinator.data.get("zones", {}))
        if "Door" in coordinator.data["zones"][z]
    ]
    async_add_entities(entities)


class ZoneDoorSensor(MieleWineEntity, BinarySensorEntity):
    """Door open/closed for a cooling zone."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator, zone: str) -> None:
        super().__init__(coordinator, f"zone{zone}_door")
        self._zone = zone
        self._attr_name = f"Zone {zone} door"

    @property
    def is_on(self) -> bool | None:
        node = self.coordinator.data.get("zones", {}).get(self._zone, {}).get("Door")
        if not node:
            return None
        return node.get("Value") == DOOR_OPEN
