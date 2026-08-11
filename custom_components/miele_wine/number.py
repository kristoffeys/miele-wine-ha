"""Settable numeric controls: light intensity and humidity level.

Each is a /Cooling node exposing {Value, Min, Max, Step}; the entity's bounds come
straight from the appliance. Target temperature is deliberately NOT here — it is the
`climate` platform's target_temperature, so exactly one entity ever writes
/Cooling/{zone}/TargetTemp.
"""

from __future__ import annotations

from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import MieleWineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    registry = er.async_get(hass)
    entities: list[NumberEntity] = []

    for z in sorted(data.get("zones", {})):
        zone = data["zones"][z]
        # Target temperature became a climate entity. Drop the number this integration
        # used to create: nothing supplies it any more, so it would sit in the registry
        # forever as an unavailable leftover that users have to delete by hand.
        if old := registry.async_get_entity_id(
            NUMBER_DOMAIN, DOMAIN, f"{coordinator.mac}_zone{z}_target_temp"
        ):
            registry.async_remove(old)
        if "PresentationLightIntensity" in zone:
            entities.append(ZoneLevelNumber(
                coordinator, z, "PresentationLightIntensity", f"Zone {z} light intensity", "mdi:brightness-6"))

    if "HumidityControl" in data.get("cooling", {}):
        entities.append(HumidityNumber(coordinator))

    async_add_entities(entities)


class ZoneLevelNumber(MieleWineEntity, NumberEntity):
    """A raw-integer /Cooling/{zone}/{field} level (e.g. light intensity 0-7)."""

    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, zone: str, field: str, name: str, icon: str) -> None:
        super().__init__(coordinator, f"zone{zone}_{field.lower()}")
        self._zone = zone
        self._field = field
        self._attr_name = name
        self._attr_icon = icon
        node = coordinator.data["zones"][zone][field]
        self._attr_native_min_value = node["Min"]
        self._attr_native_max_value = node["Max"]
        self._attr_native_step = node.get("Step", 1)

    @property
    def native_value(self) -> float | None:
        node = self.coordinator.data.get("zones", {}).get(self._zone, {}).get(self._field)
        return node.get("Value") if node else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_zone_value(
            self.coordinator.mac, self._zone, self._field, int(value))
        await self.coordinator.async_request_refresh()


class HumidityNumber(MieleWineEntity, NumberEntity):
    """Humidity control level (unit-wide /Cooling/HumidityControl). API exposes no %."""

    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "humidity_level")
        self._attr_name = "Humidity level"
        node = coordinator.data["cooling"]["HumidityControl"]
        self._attr_native_min_value = node.get("Min", 1)
        self._attr_native_max_value = node.get("Max", 3)
        self._attr_native_step = node.get("Step", 1)

    @property
    def native_value(self) -> float | None:
        node = self.coordinator.data.get("cooling", {}).get("HumidityControl")
        return node.get("Value") if node else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_cooling_value(
            self.coordinator.mac, "HumidityControl", int(value))
        await self.coordinator.async_request_refresh()
