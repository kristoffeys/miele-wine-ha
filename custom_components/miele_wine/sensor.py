"""Sensors: per-zone temperatures + target, humidity level, light intensity."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, HUMIDITY_LEVELS
from .entity import MieleWineEntity

UNUSED = -32768


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    entities: list[SensorEntity] = []

    for z in sorted(data.get("zones", {})):
        entities.append(ZoneTempSensor(coordinator, z, target=False))
        entities.append(ZoneTempSensor(coordinator, z, target=True))
        if "PresentationLightIntensity" in data["zones"][z]:
            entities.append(LightIntensitySensor(coordinator, z))

    if "HumidityControl" in data.get("cooling", {}):
        entities.append(HumidityLevelSensor(coordinator))

    async_add_entities(entities)


class ZoneTempSensor(MieleWineEntity, SensorEntity):
    """Current or target temperature for a cooling zone (centi-°C -> °C)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, zone: str, target: bool) -> None:
        kind = "target_temp" if target else "temp"
        super().__init__(coordinator, f"zone{zone}_{kind}")
        self._zone = zone
        self._field = "TargetTemp" if target else "Temp"
        self._attr_name = f"Zone {zone} {'target temperature' if target else 'temperature'}"
        if target:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> float | None:
        node = self.coordinator.data.get("zones", {}).get(self._zone, {}).get(self._field)
        if not node or node.get("Value") in (None, UNUSED):
            return None
        return round(node["Value"] / 100, 2)


class LightIntensitySensor(MieleWineEntity, SensorEntity):
    """Presentation-light intensity level (0-7)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, zone: str) -> None:
        super().__init__(coordinator, f"zone{zone}_light_intensity")
        self._zone = zone
        self._attr_name = f"Zone {zone} light intensity"

    @property
    def native_value(self) -> int | None:
        node = self.coordinator.data.get("zones", {}).get(self._zone, {}).get("PresentationLightIntensity")
        return node.get("Value") if node else None


class HumidityLevelSensor(MieleWineEntity, SensorEntity):
    """Humidity control level (1-3 -> low/medium/high). The API exposes no %."""

    _attr_translation_key = "humidity_level"
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "humidity_level")
        self._attr_name = "Humidity level"

    @property
    def native_value(self) -> str | None:
        node = self.coordinator.data.get("cooling", {}).get("HumidityControl")
        if not node:
            return None
        return HUMIDITY_LEVELS.get(node.get("Value"), str(node.get("Value")))
