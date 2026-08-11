"""Unit tests for the wine-safety state machines (no network, no Home Assistant).

`safety` takes `now` as an argument everywhere, so every duration here is exact rather
than a sleep-and-hope. T0 is an arbitrary epoch; only the deltas matter.
"""
import pytest

import safety

T0 = 1_000_000.0
MINUTE = 60.0
HOUR = 3600.0

LOW, HIGH = 10.0, 14.0
GRACE = 30 * MINUTE


def excursion(grace=GRACE):
    return safety.ExcursionTracker(LOW, HIGH, grace)


# --- ExcursionTracker: the grace period -------------------------------------

def test_in_band_is_never_an_excursion():
    t = excursion()
    for i in range(120):
        t.update(T0 + i * MINUTE, 12.0)
    assert t.is_out_of_band is False
    assert t.is_excursion is False
    assert t.excursion_seconds == 0.0
    assert t.seconds_out_of_range_today == 0.0


def test_excursion_only_trips_after_the_grace_period():
    t = excursion()
    t.update(T0, 12.0)
    # Out of band from here on. The first out-of-band reading only marks the start:
    # elapsed time is charged to the previous sample's verdict.
    t.update(T0 + MINUTE, 16.0)
    assert t.is_out_of_band is True
    assert t.is_excursion is False

    # One minute short of the grace period.
    t.update(T0 + MINUTE + GRACE - MINUTE, 16.0)
    assert t.excursion_seconds == GRACE - MINUTE
    assert t.is_excursion is False

    # Exactly at the grace period.
    t.update(T0 + MINUTE + GRACE, 16.0)
    assert t.excursion_seconds == GRACE
    assert t.is_excursion is True


def test_a_momentary_dip_never_trips():
    """A cabinet dips when the door opens; that must not alarm."""
    t = excursion()
    t.update(T0, 12.0)
    t.update(T0 + MINUTE, 9.0)          # below the band for one poll
    t.update(T0 + 2 * MINUTE, 12.0)     # back in band
    assert t.is_excursion is False
    assert t.excursion_seconds == 0.0
    assert t.seconds_out_of_range_today == MINUTE


def test_too_cold_counts_as_well():
    t = excursion(grace=0.0)
    t.update(T0, 9.9)
    assert t.is_out_of_band is True
    assert t.is_excursion is True


@pytest.mark.parametrize("temp", [10.0, 12.0, 14.0])
def test_band_edges_are_inside(temp):
    t = excursion(grace=0.0)
    t.update(T0, temp)
    assert t.is_out_of_band is False


def test_excursion_clears_on_return_to_band():
    t = excursion()
    t.update(T0, 16.0)
    t.update(T0 + 2 * GRACE, 16.0)
    assert t.is_excursion is True
    t.update(T0 + 2 * GRACE + MINUTE, 12.0)
    assert t.is_excursion is False
    assert t.is_out_of_band is False
    assert t.excursion_seconds == 0.0


# --- ExcursionTracker: the daily total --------------------------------------

def test_cumulative_time_accumulates_across_two_excursions():
    t = excursion()
    t.update(T0, 12.0)
    # First excursion: out at +1 min, back in band at +11 min -> 10 minutes charged.
    t.update(T0 + 1 * MINUTE, 16.0)
    t.update(T0 + 11 * MINUTE, 12.0)
    assert t.seconds_out_of_range_today == 10 * MINUTE
    # Back in band for a while, then a second excursion of 5 minutes.
    t.update(T0 + 30 * MINUTE, 12.0)
    t.update(T0 + 40 * MINUTE, 16.0)
    t.update(T0 + 45 * MINUTE, 12.0)
    assert t.seconds_out_of_range_today == 15 * MINUTE
    # Neither spell reached the grace period, so nothing was ever flagged.
    assert t.is_excursion is False


def test_daily_counter_resets_on_day_change():
    t = excursion()
    t.update(T0, 12.0, day_key=100)
    t.update(T0 + 10 * MINUTE, 16.0, day_key=100)
    t.update(T0 + 20 * MINUTE, 16.0, day_key=100)
    assert t.seconds_out_of_range_today == 10 * MINUTE
    # New day, still out of band: the counter starts over and only the new interval
    # is charged.
    t.update(T0 + 30 * MINUTE, 16.0, day_key=101)
    assert t.seconds_out_of_range_today == 10 * MINUTE
    # The ongoing excursion itself is not reset by the day boundary.
    assert t.excursion_seconds == 20 * MINUTE


def test_day_key_defaults_to_utc_day():
    """Without a day_key the tracker falls back to the UTC day — it has no timezone
    database. The entity passes the local day; this is only the default."""
    t = excursion()
    day = 86400.0
    midnight = day * 11
    t.update(midnight - 20 * MINUTE, 16.0)
    t.update(midnight - 10 * MINUTE, 16.0)
    assert t.seconds_out_of_range_today == 10 * MINUTE
    # First poll of the new UTC day: the counter restarts, and only the interval that
    # straddled midnight is charged to it — at a one-minute poll that is one minute.
    t.update(midnight + 1 * MINUTE, 16.0)
    assert t.seconds_out_of_range_today == 11 * MINUTE
    t.update(midnight + 11 * MINUTE, 16.0)
    assert t.seconds_out_of_range_today == 21 * MINUTE


def test_missing_reading_holds_the_verdict_and_charges_nothing():
    t = excursion()
    t.update(T0, 16.0)
    t.update(T0 + 10 * MINUTE, 16.0)
    assert t.seconds_out_of_range_today == 10 * MINUTE
    # An hour-long gap with no usable reading (missing node / -32768 sentinel).
    t.update(T0 + 70 * MINUTE, None)
    assert t.is_out_of_band is True
    assert t.seconds_out_of_range_today == 10 * MINUTE
    # Data returns: only time since the gap ended is charged.
    t.update(T0 + 75 * MINUTE, 16.0)
    assert t.seconds_out_of_range_today == 15 * MINUTE


def test_no_data_yet_is_reported():
    t = excursion()
    assert t.has_data is False
    t.update(T0, None)
    assert t.has_data is False
    t.update(T0 + MINUTE, 12.0)
    assert t.has_data is True


def test_time_going_backwards_never_charges_negative_time():
    t = excursion()
    t.update(T0, 16.0)
    t.update(T0 - 10 * MINUTE, 16.0)
    assert t.seconds_out_of_range_today == 0.0


# --- DoorTracker -----------------------------------------------------------

def test_door_trips_at_the_threshold_and_resets_on_close():
    d = safety.DoorTracker(60.0)
    d.update(T0, False)
    assert d.is_open is False
    assert d.is_left_open is False

    d.update(T0 + 10, True)
    assert d.is_open is True
    assert d.open_seconds == 0.0
    assert d.is_left_open is False

    d.update(T0 + 69, True)      # 59 s open: one short of the threshold
    assert d.open_seconds == 59
    assert d.is_left_open is False

    d.update(T0 + 70, True)      # exactly 60 s
    assert d.is_left_open is True

    d.update(T0 + 200, False)    # closed: clean reset
    assert d.is_left_open is False
    assert d.is_open is False
    assert d.open_seconds == 0.0


def test_door_reopening_starts_a_fresh_timer():
    d = safety.DoorTracker(60.0)
    d.update(T0, True)
    d.update(T0 + 300, True)
    assert d.is_left_open is True
    d.update(T0 + 301, False)
    d.update(T0 + 302, True)
    assert d.is_left_open is False
    assert d.open_seconds == 0.0


def test_door_unknown_reading_holds_the_verdict():
    d = safety.DoorTracker(60.0)
    assert d.has_data is False
    d.update(T0, None)
    assert d.has_data is False
    assert d.is_left_open is False

    d.update(T0 + 10, True)
    d.update(T0 + 100, None)     # node vanished while open
    assert d.is_open is True
    assert d.is_left_open is True
    assert d.open_seconds == 90


# --- rate_of_change --------------------------------------------------------

def test_trend_of_a_steady_climb():
    # +1 °C every half hour == +2 °C/h.
    samples = [(T0 + i * 1800, 12.0 + i) for i in range(4)]
    assert safety.rate_of_change(samples) == pytest.approx(2.0)


def test_trend_of_a_steady_fall():
    samples = [(T0 + i * HOUR, 14.0 - 0.5 * i) for i in range(5)]
    assert safety.rate_of_change(samples) == pytest.approx(-0.5)


def test_trend_of_a_flat_line_is_zero():
    samples = [(T0 + i * MINUTE, 12.0) for i in range(10)]
    assert safety.rate_of_change(samples) == pytest.approx(0.0)


def test_trend_is_a_least_squares_fit_not_first_to_last():
    """One noisy sample must not dominate: endpoints alone would read +6 °C/h here."""
    samples = [(T0, 12.0), (T0 + 1800, 12.0), (T0 + 3600, 15.0)]
    endpoints = (15.0 - 12.0) / 1.0
    fitted = safety.rate_of_change(samples)
    assert fitted == pytest.approx(3.0)
    assert fitted < endpoints * 1.5


def test_trend_ignores_missing_readings():
    samples = [(T0, 12.0), (T0 + 1800, None), (T0 + 3600, 14.0)]
    assert safety.rate_of_change(samples) == pytest.approx(2.0)


@pytest.mark.parametrize("samples", [
    [],
    [(T0, 12.0)],
    [(T0, None)],
    [(T0, None), (T0 + 60, None)],
    [(T0, 12.0), (T0, 13.0)],                    # duplicate timestamps only
    [(T0, 12.0), (T0, 13.0), (T0, 99.0)],
])
def test_trend_returns_none_instead_of_raising(samples):
    assert safety.rate_of_change(samples) is None


def test_trend_survives_a_duplicate_timestamp_among_good_samples():
    samples = [(T0, 12.0), (T0, 12.0), (T0 + 3600, 13.0)]
    assert safety.rate_of_change(samples) is not None


# --- TrendTracker ----------------------------------------------------------

def test_trend_tracker_drops_samples_outside_the_window():
    t = safety.TrendTracker(HOUR)
    for i in range(0, 121):                       # two hours at one-minute polls
        t.update(T0 + i * MINUTE, 12.0 + i * 0.01)
    assert t.sample_count == 61                   # the last hour, inclusive
    assert t.rate_per_hour == pytest.approx(0.6)  # +0.01 °C/min


def test_trend_tracker_is_none_until_two_samples():
    t = safety.TrendTracker(HOUR)
    assert t.rate_per_hour is None
    t.update(T0, 12.0)
    assert t.rate_per_hour is None
    t.update(T0 + MINUTE, 12.1)
    assert t.rate_per_hour is not None


def test_trend_tracker_skips_missing_readings():
    t = safety.TrendTracker(HOUR)
    t.update(T0, None)
    assert t.sample_count == 0
    assert t.rate_per_hour is None


# --- wire decoding ---------------------------------------------------------

@pytest.mark.parametrize("zone,expected", [
    ({"Temp": {"Value": 1234}}, 12.34),
    ({"Temp": {"Value": -50}}, -0.5),
    ({"Temp": {"Value": 0}}, 0.0),
    ({"Temp": {"Value": safety.UNUSED_TEMP}}, None),   # "not in use" sentinel
    ({"Temp": {"Value": None}}, None),
    ({"Temp": {}}, None),
    ({}, None),
    (None, None),
])
def test_zone_temp_c(zone, expected):
    assert safety.zone_temp_c(zone) == expected


@pytest.mark.parametrize("zone,expected", [
    ({"Door": {"Value": 1}}, True),
    ({"Door": {"Value": 2}}, False),
    ({"Door": {}}, None),        # node present but empty: unknown, as before this PR
    ({}, None),
    (None, None),
])
def test_zone_door_open(zone, expected):
    assert safety.zone_door_open(zone) == expected
