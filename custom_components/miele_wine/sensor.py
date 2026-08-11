"""Sensors: current temperature per cooling zone.

Kept alongside the `climate` entity on purpose — a plain sensor is what feeds history
and long-term statistics. Light intensity and humidity are settable and live on the
`number` platform; target temperature lives on `climate`.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import centi_to_celsius
from .const import DOMAIN
from .entity import MieleWineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ZoneTempSensor(coordinator, z)
        for z in sorted(coordinator.data.get("zones", {}))
        if "Temp" in coordinator.data["zones"][z]
    )


class ZoneTempSensor(MieleWineEntity, SensorEntity):
    """Current temperature for a cooling zone (centi-°C -> °C)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, zone: str) -> None:
        super().__init__(coordinator, f"zone{zone}_temp")
        self._zone = zone
        self._attr_name = f"Zone {zone} temperature"

    @property
    def native_value(self) -> float | None:
        node = self.coordinator.data.get("zones", {}).get(self._zone, {}).get("Temp")
        return centi_to_celsius(node.get("Value")) if node else None
