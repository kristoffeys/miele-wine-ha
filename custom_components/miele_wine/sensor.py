"""Sensors: current temperature per cooling zone, plus the derived wine-safety figures.

Kept alongside the `climate` entity on purpose — a plain sensor is what feeds history
and long-term statistics. Light intensity and humidity are settable and live on the
`number` platform; target temperature lives on `climate`.

The safety sensors (time out of range today, temperature trend) add no API calls: they
are state machines from safety.py fed off the `Temp` node of
GET /V2/Devices/{mac}/Cooling/{zone}/ that the coordinator already polls, so their
resolution is the poll interval.
"""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import centi_to_celsius
from .const import (
    DOMAIN,
    EXCURSION_GRACE_SECONDS,
    SAFE_TEMP_HIGH_C,
    SAFE_TEMP_LOW_C,
    TREND_WINDOW_SECONDS,
)
from .entity import MieleWineEntity
from .safety import ExcursionTracker, TrendTracker, zone_temp_c


def _zone(coordinator, zone: str) -> dict[str, Any]:
    return coordinator.data.get("zones", {}).get(zone, {})


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    zones = coordinator.data.get("zones", {})
    entities: list[SensorEntity] = []
    for z in sorted(zones):
        if "Temp" in zones[z]:
            entities.append(ZoneTempSensor(coordinator, z))
            entities.append(ZoneOutOfRangeTodaySensor(coordinator, z))
            entities.append(ZoneTempTrendSensor(coordinator, z))
    async_add_entities(entities)


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
        node = _zone(self.coordinator, self._zone).get("Temp")
        return centi_to_celsius(node.get("Value")) if node else None


class ZoneOutOfRangeTodaySensor(MieleWineEntity, SensorEntity):
    """Minutes this zone has spent outside the safe band today.

    Grace-independent on purpose: five short excursions are as bad for the wine as one
    long one, so this counts every minute out of band even when the problem sensor
    stayed off. TOTAL_INCREASING because it resets at local midnight.
    """

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:thermometer-alert"

    def __init__(self, coordinator, zone: str) -> None:
        super().__init__(coordinator, f"zone{zone}_out_of_range_today")
        self._zone = zone
        self._attr_name = f"Zone {zone} time out of range today"
        self._tracker = ExcursionTracker(
            SAFE_TEMP_LOW_C, SAFE_TEMP_HIGH_C, EXCURSION_GRACE_SECONDS
        )
        self._feed()

    def _feed(self) -> None:
        # Two clocks on purpose: monotonic() for the durations, so an NTP or DST step
        # cannot invent or erase out-of-range time, and the local calendar day for the
        # reset, so "today" means the user's day rather than a UTC one.
        self._tracker.update(
            time.monotonic(),
            zone_temp_c(_zone(self.coordinator, self._zone)),
            day_key=dt_util.now().toordinal(),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._feed()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        return round(self._tracker.seconds_out_of_range_today / 60, 1)


class ZoneTempTrendSensor(MieleWineEntity, SensorEntity):
    """Temperature slope in °C/h over the trend window.

    Diagnostic rather than a headline figure: a failing compressor shows up as a steady
    climb long before the absolute temperature crosses any alarm line, but the number
    only means something to someone looking for that.
    """

    _attr_native_unit_of_measurement = "°C/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator, zone: str) -> None:
        super().__init__(coordinator, f"zone{zone}_temp_trend")
        self._zone = zone
        self._attr_name = f"Zone {zone} temperature trend"
        self._tracker = TrendTracker(TREND_WINDOW_SECONDS)
        self._feed()

    def _feed(self) -> None:
        self._tracker.update(time.monotonic(), zone_temp_c(_zone(self.coordinator, self._zone)))

    @callback
    def _handle_coordinator_update(self) -> None:
        self._feed()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float | None:
        # None until two readings exist — a slope from one sample would be a fiction.
        rate = self._tracker.rate_per_hour
        return None if rate is None else round(rate, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"samples": self._tracker.sample_count}
