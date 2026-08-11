"""Entity discovery from the self-describing GET /V2/Devices/{mac}/Cooling/ payload.

Every node under /Cooling/ enumerates its own legal values:

    {"Value": 2, "SetValues": [1], "AllValues": [1, 2]}

`AllValues` is the full legal set, `SetValues` the subset the appliance will accept
*right now* (it shrinks to exclude the current value, and changes on every poll).
Entity creation is therefore driven off `AllValues` only — keying entities on
`SetValues` would make them appear and disappear as the appliance's state moves.

Deriving entities from that enumeration instead of a hardcoded table is what lets
this integration work on Miele cooling appliances it has never seen: a fridge, a
freezer, a wine+freezer combo, or a /Cooling/ field that was not present in the
capture this integration was reverse-engineered from.

Deliberately Home-Assistant-free — tests/conftest.py puts this package on sys.path
and imports the module standalone, so it must not import homeassistant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator

# Miele's on/off convention across this whole API: 1 = on/enabled/open,
# 2 = off/disabled/closed. See api.LIGHT_ON / api.LIGHT_OFF and
# binary_sensor.DOOR_OPEN — same encoding, different resources.
TOGGLE_ON = 1
TOGGLE_OFF = 2

# Nodes this integration shipped as switches before discovery existed. If a
# firmware omits AllValues on one of them we keep the switch anyway (with the
# conventional 1/2 pair) so no already-registered entity disappears on upgrade.
KNOWN_TOGGLES = frozenset({"Sabbath", "ChildProof", "AirFilter"})

# Names the switch platform must not claim. All of them are still yielded by
# iter_cooling_nodes — the exclusion is switch-specific, not a blanket skip.
#
# Do not "helpfully" shorten this set. Every entry is here for a reason:
#   PresentationLight  — the light entity owns it.
#   HumidityControl    — the number entity owns it.
#   TempUnit           — an enumeration, not a toggle: "Temperature unit: on" is
#                        meaningless, and this field drives what the appliance's own
#                        front panel displays, so an accidental toggle is a visible
#                        configuration change on the physical unit.
#   PresentationType   — likewise an enumeration; a switch would misrepresent it.
# The last two belong to a future select platform. Excluding them costs nothing and
# leaves no trace; creating them would write a unique_id into the entity registry
# that the select platform would then have to awkwardly reuse or orphan. Cheap to
# add later, expensive to retract — so they stay out until there is a select entity
# to own them. classify_node() still reports them as "select" once they enumerate
# three or more values, so nothing has to re-derive that.
NOT_SWITCHES = frozenset(
    {"PresentationLight", "HumidityControl", "TempUnit", "PresentationType"}
)

# Labels for the nodes we have actually seen. Anything else gets the CamelCase
# fallback below, which is deliberately dumb but readable.
FRIENDLY_NAMES = {
    "Sabbath": "Sabbath mode",
    "ChildProof": "Child lock",
    "AirFilter": "Active air filter",
    "PresentationLight": "Presentation light",
    "PresentationType": "Presentation type",
    "TempUnit": "Temperature unit",
    "HumidityControl": "Humidity level",
}

# CamelCase / ACRONYM / digit-run splitter for names nobody has documented yet:
# "SuperCooling" -> Super, Cooling;  "ECOMode" -> ECO, Mode;  "Zone2Temp" -> Zone, 2, Temp.
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|\d+")


@dataclass(frozen=True)
class CoolingSwitchSpec:
    """Everything the switch platform needs for one /Cooling/{name} toggle."""

    name: str            # the wire field name, used in PUT /Cooling/{name}
    friendly: str
    on_value: int
    off_value: int

    @property
    def key(self) -> str:
        """The entity key half of the unique_id.

        MUST stay f"cooling_{name.lower()}": entity.py builds unique_id as
        f"{mac}_{key}", so any change here would orphan every existing switch and
        take its history, customisations and automation references with it.
        """
        return f"cooling_{self.name.lower()}"


def _all_values(node: Any) -> list[int]:
    """The node's enumerated legal values, or [] when it does not usably report any.

    Anything that is not a list of plain ints is treated as "not reported": the
    firmware is free to send shapes we have never seen, and a surprise must not
    raise in the middle of platform setup. bools are excluded explicitly because
    `isinstance(True, int)` is True in Python.
    """
    values = node.get("AllValues") if isinstance(node, dict) else None
    if not isinstance(values, list):
        return []
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return []
    # Duplicates would misreport the arity; order is not significant to us.
    return sorted(set(values))


def _has_bounds(node: Any) -> bool:
    """True when the node describes a numeric range.

    Step is not required: number.py already defaults it (HumidityControl is read
    with node.get("Step", 1)), so a Min/Max pair alone is a usable number.
    """
    if not isinstance(node, dict):
        return False
    return all(
        isinstance(node.get(k), (int, float)) and not isinstance(node.get(k), bool)
        for k in ("Min", "Max")
    )


def toggle_values(node: Any) -> tuple[int, int] | None:
    """The (on, off) pair for a two-valued node, or None if it is not a toggle.

    Only the conventional {1, 2} pair is accepted, always returned as (on=1, off=2)
    regardless of the order the appliance listed them in. A different pair (say
    {0, 1}) is refused rather than guessed at: writing the wrong value to a real
    appliance is worse than exposing no entity, and check_write_result() would only
    surface the mistake after the fact.
    """
    values = _all_values(node)
    if len(values) != 2 or set(values) != {TOGGLE_ON, TOGGLE_OFF}:
        return None
    return (TOGGLE_ON, TOGGLE_OFF)


def classify_node(name: str, node: Any) -> str | None:
    """Which platform shape a /Cooling/{name} node fits: toggle, select, number.

    Returns None for anything unrecognised — the caller skips it. Unknown is the
    expected case on appliances this integration has never seen, not an error.
    """
    if not isinstance(node, dict):
        return None

    values = _all_values(node)
    if len(values) >= 3:
        # Three or more enumerated values is a choice, not a switch. The select
        # platform is not shipped yet; classifying it means callers can find these
        # without another sweep of the payload.
        return "select"
    if toggle_values(node) is not None:
        return "toggle"
    if not values and name in KNOWN_TOGGLES:
        # No enumeration at all: fall back to what this integration has always
        # done for these three. Only when the appliance says nothing — if it does
        # report values and they are not {1, 2}, we believe the appliance and skip.
        return "toggle"
    if not values and _has_bounds(node):
        return "number"
    return None


def iter_cooling_nodes(cooling: Any) -> Iterator[tuple[str, dict[str, Any], str]]:
    """Yield (name, node, kind) for every classifiable node in a /Cooling/ body.

    Skipped: digit-named keys (those are zone sub-resources, fetched separately as
    /Cooling/{zone}/ and owned by the per-zone platforms), non-dict entries such as
    the payload's scalar metadata, and nodes classify_node() does not recognise.
    """
    if not isinstance(cooling, dict):
        return
    for name in sorted(cooling):
        if not isinstance(name, str) or name.isdigit():
            continue
        node = cooling[name]
        if not isinstance(node, dict):
            continue
        kind = classify_node(name, node)
        if kind is None:
            continue
        yield name, node, kind


def friendly_name(name: str) -> str:
    """A display label for a /Cooling/ field name.

    Known fields get a curated label; anything else gets its CamelCase split into
    sentence case ("SuperCooling" -> "Super cooling") so an unmet field still shows
    up readably instead of as a raw wire name.
    """
    if name in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[name]
    words = _WORD.findall(name)
    if not words:
        return name
    # Keep acronyms shouting ("ECO"), lowercase ordinary words after the first.
    parts = [w if w.isupper() and len(w) > 1 else w.lower() for w in words]
    first = parts[0]
    parts[0] = first if first.isupper() and len(first) > 1 else first.capitalize()
    return " ".join(parts)


def cooling_switch_specs(cooling: Any) -> list[CoolingSwitchSpec]:
    """Every /Cooling/ node the switch platform should expose, in name order."""
    specs = []
    for name, node, kind in iter_cooling_nodes(cooling):
        if kind != "toggle" or name in NOT_SWITCHES:
            continue
        # A KNOWN_TOGGLES node with no enumeration classifies as a toggle without
        # toggle_values() being able to derive the pair; use the convention.
        on_value, off_value = toggle_values(node) or (TOGGLE_ON, TOGGLE_OFF)
        specs.append(
            CoolingSwitchSpec(
                name=name,
                friendly=friendly_name(name),
                on_value=on_value,
                off_value=off_value,
            )
        )
    return specs
