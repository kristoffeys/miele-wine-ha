"""Per-zone door binary sensors (Door.Value: 1=open, 2=closed) and the derived
wine-safety problem sensors.

The safety sensors add no API calls: they are state machines (see safety.py) fed from
the `Temp` and `Door` nodes of GET /V2/Devices/{mac}/Cooling/{zone}/ that the
coordinator already polls. Their resolution is therefore the poll interval — a door
opened and closed between two polls is invisible, and an alert trips on the first poll
at or after its threshold.
"""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    DOOR_OPEN_THRESHOLD_SECONDS,
    EXCURSION_GRACE_SECONDS,
    SAFE_TEMP_HIGH_C,
    SAFE_TEMP_LOW_C,
)
from .entity import MieleWineEntity
from .safety import DoorTracker, ExcursionTracker, zone_door_open, zone_temp_c


def _zone(coordinator, zone: str) -> dict[str, Any]:
    return coordinator.data.get("zones", {}).get(zone, {})


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    zones = coordinator.data.get("zones", {})
    entities: list[BinarySensorEntity] = []
    for z in sorted(zones):
        if "Door" in zones[z]:
            entities.append(ZoneDoorSensor(coordinator, z))
            entities.append(ZoneDoorLeftOpenSensor(coordinator, z))
        if "Temp" in zones[z]:
            entities.append(ZoneExcursionSensor(coordinator, z))
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
        return zone_door_open(_zone(self.coordinator, self._zone))


class ZoneExcursionSensor(MieleWineEntity, BinarySensorEntity):
    """On when a zone has been outside the safe band for longer than the grace period.

    Holds its own ExcursionTracker rather than sharing one with the "time out of range
    today" sensor: the tracker is a cheap deterministic state machine fed from the same
    data at the same moment, so two instances agree, and that avoids a cross-platform
    singleton or a change to coordinator.py.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, zone: str) -> None:
        super().__init__(coordinator, f"zone{zone}_excursion")
        self._zone = zone
        self._attr_name = f"Zone {zone} temperature excursion"
        self._tracker = ExcursionTracker(
            SAFE_TEMP_LOW_C, SAFE_TEMP_HIGH_C, EXCURSION_GRACE_SECONDS
        )
        self._feed()

    def _feed(self) -> None:
        # monotonic(), not the wall clock: this measures a duration, and a clock step
        # (NTP, DST) must not invent or erase excursion time. No day_key — this entity
        # exposes only the live verdict; the daily counter is the sensor platform's.
        self._tracker.update(time.monotonic(), zone_temp_c(_zone(self.coordinator, self._zone)))

    @callback
    def _handle_coordinator_update(self) -> None:
        self._feed()
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool | None:
        if not self._tracker.has_data:
            return None
        return self._tracker.is_excursion

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "safe_low_c": SAFE_TEMP_LOW_C,
            "safe_high_c": SAFE_TEMP_HIGH_C,
            "out_of_band": self._tracker.is_out_of_band,
            "excursion_minutes": round(self._tracker.excursion_seconds / 60, 1),
        }


class ZoneDoorLeftOpenSensor(MieleWineEntity, BinarySensorEntity):
    """On once a zone's door has been open past the threshold."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, zone: str) -> None:
        super().__init__(coordinator, f"zone{zone}_door_left_open")
        self._zone = zone
        self._attr_name = f"Zone {zone} door left open"
        self._tracker = DoorTracker(DOOR_OPEN_THRESHOLD_SECONDS)
        self._feed()

    def _feed(self) -> None:
        self._tracker.update(
            time.monotonic(), zone_door_open(_zone(self.coordinator, self._zone))
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._feed()
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool | None:
        if not self._tracker.has_data:
            return None
        return self._tracker.is_left_open

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"open_minutes": round(self._tracker.open_seconds / 60, 1)}
