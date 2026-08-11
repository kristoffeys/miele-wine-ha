"""Argument validation for the generic /Cooling setter services.

Deliberately imports nothing from homeassistant: CI installs only aiohttp + pytest and
imports the component's modules standalone (see tests/conftest.py), so keeping these
checks HA-free is what makes them testable at all.

These values are interpolated straight into a request path —
PUT /V2/Devices/{mac}/Cooling/{name} and /Cooling/{zone}/{name} — so treat the checks
as a path-traversal guard, not input polish: a "/" or ".." inside `name` would escape
/Cooling/ and address an unrelated resource on the appliance, and the API happily
accepts whatever path we hand it.
"""

from __future__ import annotations

import re
from typing import Any

# /Cooling node names are bare CamelCase identifiers (PresentationLight, Sabbath,
# HumidityControl, TargetTemp, ...). No separator of any kind is allowed, which is what
# rejects "a/b", "../x" and "a.b" as well as "" and "1abc".
NODE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")

# Zone keys are the digit-string keys of the /Cooling/ body ("1", "2"); the coordinator
# picks them out with str.isdigit(). This is stricter on purpose: str.isdigit() is true
# for non-ASCII digits like "١", which would not resolve to a zone.
ZONE_RE = re.compile(r"[0-9]+")


class InvalidServiceData(ValueError):
    """A service argument failed validation — surface it to the caller, do not retry."""


def _fullmatch(pattern: re.Pattern[str], value: str) -> bool:
    r"""fullmatch(), never match() with a "$" anchor.

    "$" also matches just before a trailing newline, so "Sabbath\n" would slip through
    a "^...$" pattern and put a control character into the URL path.
    """
    return pattern.fullmatch(value) is not None


def validate_node_name(name: Any) -> str:
    """Return `name` if it is a safe /Cooling node name, else raise."""
    if not isinstance(name, str):
        raise InvalidServiceData(f"name must be a string, got {type(name).__name__}")
    if not _fullmatch(NODE_NAME_RE, name):
        raise InvalidServiceData(
            f"invalid /Cooling node name {name!r}: expected letters and digits only, "
            "starting with a letter (e.g. 'Sabbath', 'HumidityControl')"
        )
    return name


def validate_zone(zone: Any) -> str:
    """Return `zone` as its digit-string API key, else raise.

    Ints are accepted because YAML turns `zone: 1` into an int long before it reaches
    us; the wire form is always the string. bool is rejected first — it is an int
    subclass, and str(True) is not a zone.
    """
    if isinstance(zone, bool):
        raise InvalidServiceData("zone must be a digit string, got a boolean")
    if isinstance(zone, int):
        zone = str(zone)
    if not isinstance(zone, str):
        raise InvalidServiceData(f"zone must be a string, got {type(zone).__name__}")
    if not _fullmatch(ZONE_RE, zone):
        raise InvalidServiceData(
            f"invalid zone {zone!r}: expected digits only (the API's zone keys are '1', '2', ...)"
        )
    return zone


def validate_value(value: Any) -> int:
    """Return `value` if it is a plain int, else raise.

    The /Cooling body is {"Value": <int>}; a float or a string would be serialised as
    such and rejected by the appliance, and bool (an int subclass in Python) would go
    out as JSON `true`. Integral values typed in the UI arrive here as ints: JavaScript
    has no int/float split, so JSON.stringify(1) is "1" and json.loads gives int.
    """
    if isinstance(value, bool):
        raise InvalidServiceData("value must be an integer, got a boolean")
    if not isinstance(value, int):
        raise InvalidServiceData(
            f"value must be an integer, got {type(value).__name__} ({value!r})"
        )
    return value
