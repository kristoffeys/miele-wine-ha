"""Polling-interval policy for the Miele consumer cloud (rest-eu.domestic.miele-iot.com).

Deliberately free of any Home Assistant import: CI installs only aiohttp + pytest and
puts this directory on sys.path (tests/conftest.py), so the rules below can be unit
tested as plain functions. The coordinator supplies the clock and the observed state.

Why adapt at all: the consumer cloud throws intermittent nginx 500s (see FINDINGS,
2026-08-09) and rate-limits, so a fixed interval is both too chatty for an idle cabinet
and too slow right after a write — the appliance needs a few seconds before
GET /Cooling/ reflects a PUT, and a 60 s interval leaves the UI stale until then.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# The cabinet takes a few seconds to report a written value back on GET /Cooling/, so
# poll hard for a short while after a successful write and while a door is open (the
# only time the temperatures actually move).
FAST_INTERVAL = 10

# How long after a successful write we stay in the fast lane.
WRITE_SETTLE_WINDOW = 60.0

# Ceiling for error backoff. A cloud that is 500-ing gets checked at most every 10 min.
MAX_BACKOFF_INTERVAL = 600

# Doubling past this many consecutive errors cannot change the outcome (the cap has
# already been hit); bounding the shift keeps a runaway counter from building a bignum.
_MAX_BACKOFF_SHIFT = 16

# Door.Value from GET /Cooling/{zone}/: 1 = open, 2 = closed. Duplicated from
# binary_sensor.py on purpose — that module imports homeassistant and this one must not.
DOOR_OPEN = 1


def next_interval(
    base: int,
    *,
    adaptive: bool,
    door_open: bool,
    seconds_since_write: float | None,
    consecutive_errors: int,
) -> int:
    """Return the number of seconds to wait before the next poll.

    ``base`` is the user's configured scan interval. With ``adaptive`` off the base is
    returned unchanged, which is exactly the pre-options behaviour of the integration.

    Precedence is deliberate: backoff outranks the fast cases. An open door or a fresh
    write must not make us hammer a cloud that is already failing.
    """
    if not adaptive:
        return base

    if consecutive_errors > 0:
        shift = min(consecutive_errors, _MAX_BACKOFF_SHIFT)
        backoff = min(base * 2**shift, MAX_BACKOFF_INTERVAL)
        # Never end up polling faster than the user asked for: with a base above the
        # cap, the cap itself would otherwise be an increase in traffic on failure.
        return max(base, backoff)

    if seconds_since_write is not None and seconds_since_write < WRITE_SETTLE_WINDOW:
        return _fast(base)

    if door_open:
        return _fast(base)

    return base


def any_door_open(zones: Mapping[str, Any] | None) -> bool:
    """True if any zone reports its door open, given the coordinator's ``zones`` map.

    Missing or malformed nodes read as closed: an absent Door is not evidence of an open
    one, and guessing "open" would pin the integration to the fast interval forever.
    """
    if not zones:
        return False
    for zone in zones.values():
        if not isinstance(zone, Mapping):
            continue
        door = zone.get("Door")
        if isinstance(door, Mapping) and door.get("Value") == DOOR_OPEN:
            return True
    return False


def _fast(base: int) -> int:
    # A "fast" poll must never be slower than the configured base, but it also must not
    # overtake a base that is already below the fast interval.
    return min(FAST_INTERVAL, base)
