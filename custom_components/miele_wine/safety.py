"""Wine-safety logic: temperature excursions, door-left-open, temperature trend.

Derived entirely from the `Temp` and `Door` nodes the coordinator already polls from
GET /V2/Devices/{mac}/Cooling/{zone}/ — this module speaks no protocol and opens no
connection, so it adds zero API calls.

Deliberately Home-Assistant-free and clock-free: `now` is always an argument, never read
from time.time()/datetime.now() in here, so CI (which installs no homeassistant — see
tests/conftest.py) can drive every state machine deterministically. It also imports no
sibling module of this integration, because the test suite imports it standalone
(`import safety`) where relative imports do not resolve.

Why any state is kept at all: wine is damaged by *sustained* deviation and by thermal
cycling, not by one momentary reading. The answer to "is my collection at risk" is a
duration and a slope, and both need memory between polls.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Sequence

SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0

# Wire values of the two nodes this module consumes.
UNUSED_TEMP = -32768  # appliance sentinel for "this sensor/zone is not in use"
DOOR_OPEN = 1         # Door.Value: 1 = open, 2 = closed


def zone_temp_c(zone: dict[str, Any] | None) -> float | None:
    """Read a zone's current temperature in °C, or None when there is no usable value.

    Lives here rather than in an entity so the decode is covered by CI (which cannot
    import homeassistant): temperatures are centi-°C integers, and -32768 is the
    "not in use" sentinel, not a real -327.68 °C reading.
    """
    node = (zone or {}).get("Temp")
    if not node or node.get("Value") in (None, UNUSED_TEMP):
        return None
    return node["Value"] / 100


def zone_door_open(zone: dict[str, Any] | None) -> bool | None:
    """Whether a zone's door is open, or None when the node is absent."""
    node = (zone or {}).get("Door")
    if not node:
        return None
    return node.get("Value") == DOOR_OPEN


def rate_of_change(samples: Sequence[tuple[float, float | None]]) -> float | None:
    """Least-squares slope of temperature against time, in °C per hour.

    Least squares rather than (last - first) / elapsed: at a one-minute poll a single
    noisy reading would dominate a two-point slope, and a failing compressor announces
    itself as a trend long before any absolute value crosses an alarm line.

    Returns None — never raises — when there is nothing to fit: no samples, a single
    sample, only None readings, or every timestamp identical (which would otherwise
    divide by a zero-variance denominator).
    """
    points = [(float(t), float(v)) for t, v in samples if v is not None]
    if len(points) < 2:
        return None
    count = len(points)
    mean_t = sum(t for t, _ in points) / count
    mean_v = sum(v for _, v in points) / count
    variance = sum((t - mean_t) ** 2 for t, _ in points)
    if variance == 0:
        return None
    slope = sum((t - mean_t) * (v - mean_v) for t, v in points) / variance
    return slope * SECONDS_PER_HOUR


class ExcursionTracker:
    """How long a zone has been outside the safe temperature band.

    Fed once per poll. Elapsed time is charged to the *previous* sample's verdict, which
    is the only honest reading of a one-minute cloud poll: we know the temperature at t0
    and at t1, not what it did in between. That makes the accounting deliberately
    conservative — the interval in which the zone comes back into band still counts as
    out of range.
    """

    def __init__(self, low_c: float, high_c: float, grace_seconds: float) -> None:
        self._low = low_c
        self._high = high_c
        self._grace = grace_seconds
        self._last_now: float | None = None
        self._out_of_band = False
        self._excursion_seconds = 0.0
        self._today_seconds = 0.0
        self._day_key: int | None = None
        self._has_data = False

    def update(self, now: float, temp_c: float | None, day_key: int | None = None) -> None:
        """Feed one reading. `day_key` identifies the calendar day for the daily total;
        the caller passes a local-timezone day so the reset lands at local midnight, and
        the UTC day is only the fallback (this module has no timezone database)."""
        key = int(now // SECONDS_PER_DAY) if day_key is None else day_key
        if self._day_key is None:
            self._day_key = key
        elif key != self._day_key:
            # A new day starts at zero. The interval straddling midnight is charged to
            # the new day (at most one poll); the sensor is TOTAL_INCREASING, so Home
            # Assistant's statistics treat the drop as a reset rather than a spike.
            self._day_key = key
            self._today_seconds = 0.0

        elapsed = 0.0 if self._last_now is None else max(0.0, now - self._last_now)
        self._last_now = now

        if temp_c is None:
            # No reading (missing node, or the -32768 "not in use" sentinel). Hold the
            # current verdict but charge nothing: we cannot claim the wine was out of
            # range across a gap we have no data for.
            return
        self._has_data = True

        if self._out_of_band:
            self._excursion_seconds += elapsed
            self._today_seconds += elapsed

        self._out_of_band = temp_c < self._low or temp_c > self._high
        if not self._out_of_band:
            self._excursion_seconds = 0.0

    @property
    def has_data(self) -> bool:
        """False until a real reading has been seen, so entities can report unknown."""
        return self._has_data

    @property
    def is_out_of_band(self) -> bool:
        """The latest reading is outside the band, grace period notwithstanding."""
        return self._out_of_band

    @property
    def excursion_seconds(self) -> float:
        """Accrued seconds in the current unbroken spell out of band (0 when in band)."""
        return self._excursion_seconds

    @property
    def is_excursion(self) -> bool:
        """Out of band, and there long enough to matter."""
        return self._out_of_band and self._excursion_seconds >= self._grace

    @property
    def seconds_out_of_range_today(self) -> float:
        """Cumulative seconds out of band since the last day change, grace-independent —
        five short excursions are as bad for the wine as one long one."""
        return self._today_seconds


class DoorTracker:
    """Whether a zone's door has been open past a threshold.

    Keeps the instant the door was first seen open rather than integrating intervals, so
    a missed poll cannot lose accrued time.
    """

    def __init__(self, threshold_seconds: float) -> None:
        self._threshold = threshold_seconds
        self._opened_at: float | None = None
        self._now: float | None = None
        self._has_data = False

    def update(self, now: float, is_open: bool | None) -> None:
        self._now = now
        if is_open is None:
            return  # unknown reading: hold the current verdict
        self._has_data = True
        if is_open:
            if self._opened_at is None:
                self._opened_at = now
        else:
            self._opened_at = None

    @property
    def has_data(self) -> bool:
        return self._has_data

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None

    @property
    def open_seconds(self) -> float:
        if self._opened_at is None or self._now is None:
            return 0.0
        return max(0.0, self._now - self._opened_at)

    @property
    def is_left_open(self) -> bool:
        return self._opened_at is not None and self.open_seconds >= self._threshold


class TrendTracker:
    """Rolling window of readings behind rate_of_change()."""

    def __init__(self, window_seconds: float) -> None:
        self._window = window_seconds
        self._samples: deque[tuple[float, float]] = deque()

    def update(self, now: float, temp_c: float | None) -> None:
        if temp_c is not None:
            self._samples.append((now, float(temp_c)))
        while self._samples and now - self._samples[0][0] > self._window:
            self._samples.popleft()

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    @property
    def rate_per_hour(self) -> float | None:
        return rate_of_change(list(self._samples))
