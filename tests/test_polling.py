"""Unit tests for the polling-interval policy (no network, no Home Assistant)."""
import pytest

import polling

BASE = 60


def interval(**kwargs):
    """next_interval() with the idle defaults, overridden per test."""
    base = kwargs.pop("base", BASE)
    args = {
        "adaptive": True,
        "door_open": False,
        "seconds_since_write": None,
        "consecutive_errors": 0,
    }
    args.update(kwargs)
    return polling.next_interval(base, **args)


# --- adaptive disabled: today's behaviour, exactly -----------------------------
@pytest.mark.parametrize("door_open", [False, True])
@pytest.mark.parametrize("seconds_since_write", [None, 0.0, 5.0, 10_000.0])
@pytest.mark.parametrize("consecutive_errors", [0, 1, 9])
def test_adaptive_off_always_returns_base(door_open, seconds_since_write, consecutive_errors):
    assert (
        polling.next_interval(
            BASE,
            adaptive=False,
            door_open=door_open,
            seconds_since_write=seconds_since_write,
            consecutive_errors=consecutive_errors,
        )
        == BASE
    )


# --- the fast cases -----------------------------------------------------------
def test_idle_returns_base():
    assert interval() == BASE


def test_door_open_is_fast():
    assert interval(door_open=True) == polling.FAST_INTERVAL


def test_recent_write_is_fast():
    assert interval(seconds_since_write=0.0) == polling.FAST_INTERVAL
    assert interval(seconds_since_write=59.0) == polling.FAST_INTERVAL


def test_old_write_returns_base():
    assert interval(seconds_since_write=polling.WRITE_SETTLE_WINDOW) == BASE
    assert interval(seconds_since_write=3600.0) == BASE


def test_no_write_yet_is_handled():
    # None means "no write in this run", not "a write just happened".
    assert interval(seconds_since_write=None) == BASE


def test_fast_never_slower_than_a_tiny_base():
    # A base below the fast interval wins: fast must not slow polling down.
    assert interval(base=5, door_open=True) == 5


# --- error backoff ------------------------------------------------------------
def test_backoff_doubles_per_error():
    assert interval(consecutive_errors=1) == 120
    assert interval(consecutive_errors=2) == 240
    assert interval(consecutive_errors=3) == 480


def test_backoff_is_capped():
    assert interval(consecutive_errors=4) == polling.MAX_BACKOFF_INTERVAL
    assert interval(consecutive_errors=50) == polling.MAX_BACKOFF_INTERVAL
    # An absurd counter must not build a bignum or exceed the cap.
    assert interval(consecutive_errors=10_000) == polling.MAX_BACKOFF_INTERVAL


def test_backoff_never_polls_faster_than_base():
    # base above the cap: failing must never increase traffic.
    assert interval(base=900, consecutive_errors=1) == 900
    assert interval(base=900, consecutive_errors=9) == 900


def test_backoff_beats_door_open():
    assert interval(door_open=True, consecutive_errors=1) == 120


def test_backoff_beats_recent_write():
    assert interval(seconds_since_write=1.0, consecutive_errors=2) == 240


def test_backoff_beats_both():
    assert interval(door_open=True, seconds_since_write=0.0, consecutive_errors=3) == 480


def test_recovered_from_errors_returns_base():
    assert interval(consecutive_errors=0) == BASE


# --- door detection over the coordinator's zones map ---------------------------
def test_any_door_open_true():
    zones = {"0": {"Door": {"Value": 2}}, "1": {"Door": {"Value": 1}}}
    assert polling.any_door_open(zones) is True


def test_any_door_open_all_closed():
    assert polling.any_door_open({"0": {"Door": {"Value": 2}}}) is False


def test_any_door_open_tolerates_missing_and_junk():
    # A missing/malformed Door is not evidence of an open door.
    assert polling.any_door_open(None) is False
    assert polling.any_door_open({}) is False
    assert polling.any_door_open({"0": {}}) is False
    assert polling.any_door_open({"0": {"Door": None}}) is False
    assert polling.any_door_open({"0": {"Door": {}}}) is False
    assert polling.any_door_open({"0": "not-a-mapping"}) is False
