"""Climate: one thermostat per cooling zone.

Reads GET /V2/Devices/{mac}/Cooling/{zone}/ (already polled by the coordinator, so
this platform costs no extra API calls) and writes PUT /Cooling/{zone}/TargetTemp —
the only write path this appliance accepts for temperature. Values on the wire are
centi-°C integers; see api.centi_to_celsius / api.celsius_to_centi.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import celsius_to_centi, centi_to_celsius
from .const import DOMAIN
from .entity import MieleWineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ZoneClimate(coordinator, z)
        for z in sorted(coordinator.data.get("zones", {}))
        if "TargetTemp" in coordinator.data["zones"][z]
    )


class ZoneClimate(MieleWineEntity, ClimateEntity):
    """A cooling zone as a thermostat.

    The API exposes no power/mode node for a zone — a wine cabinet cools whenever it
    is plugged in — so hvac_mode is the single fixed value COOL rather than an
    invented on/off. Only the target temperature is settable.
    """

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.COOL]
    _attr_hvac_mode = HVACMode.COOL
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(self, coordinator, zone: str) -> None:
        super().__init__(coordinator, f"zone{zone}_climate")
        self._zone = zone
        self._attr_name = f"Zone {zone}"
        # Bounds are firmware-fixed, so read them once at setup (as the number
        # platform did). Skip any field a future firmware omits and let HA fall back
        # to its own defaults rather than inventing a range.
        node = coordinator.data["zones"][zone]["TargetTemp"]
        if (low := centi_to_celsius(node.get("Min"))) is not None:
            self._attr_min_temp = low
        if (high := centi_to_celsius(node.get("Max"))) is not None:
            self._attr_max_temp = high
        if (step := centi_to_celsius(node.get("Step"))) is not None:
            self._attr_target_temperature_step = step

    def _node(self, name: str) -> dict[str, Any] | None:
        return self.coordinator.data.get("zones", {}).get(self._zone, {}).get(name)

    @property
    def current_temperature(self) -> float | None:
        node = self._node("Temp")
        return centi_to_celsius(node.get("Value")) if node else None

    @property
    def target_temperature(self) -> float | None:
        node = self._node("TargetTemp")
        return centi_to_celsius(node.get("Value")) if node else None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (value := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.coordinator.client.set_zone_value(
            self.coordinator.mac, self._zone, "TargetTemp", celsius_to_centi(value))
        await self.coordinator.async_request_refresh()
