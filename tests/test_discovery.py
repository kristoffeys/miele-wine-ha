"""Unit tests for /Cooling/ capability discovery (no network, no Home Assistant)."""
import pytest

import discovery

# Shape observed on the KWTUS 7096E: every node enumerates its legal values, and
# SetValues is the momentarily-writable subset (here: currently off, may be set to on).
TOGGLE_NODE = {"Value": 2, "SetValues": [1], "AllValues": [1, 2]}

# A realistic unit-level body: named nodes plus the digit-keyed zone sub-resources
# that coordinator.py fetches separately as /Cooling/{zone}/.
COOLING = {
    "Sabbath": {"Value": 2, "SetValues": [1], "AllValues": [1, 2]},
    "ChildProof": {"Value": 2, "SetValues": [1], "AllValues": [1, 2]},
    "AirFilter": {"Value": 1, "SetValues": [2], "AllValues": [1, 2]},
    "PresentationLight": {"Value": 2, "SetValues": [1], "AllValues": [1, 2]},
    "HumidityControl": {"Value": 2, "Min": 1, "Max": 3, "Step": 1},
    "0": {"Temp": {"Value": 1200}},
    "1": {"Temp": {"Value": 1400}},
}


@pytest.mark.parametrize("name", ["Sabbath", "ChildProof", "AirFilter"])
def test_known_toggles_classify_as_toggles_with_1_2(name):
    node = COOLING[name]
    assert discovery.classify_node(name, node) == "toggle"
    assert discovery.toggle_values(node) == (1, 2)


def test_toggle_pair_is_normalised_regardless_of_listed_order():
    assert discovery.toggle_values({"AllValues": [2, 1]}) == (1, 2)


def test_three_or_more_values_is_a_select_not_a_toggle():
    node = {"Value": 1, "SetValues": [2, 3], "AllValues": [1, 2, 3]}
    assert discovery.classify_node("PresentationType", node) == "select"
    assert discovery.toggle_values(node) is None
    # A select must never reach the switch platform.
    assert discovery.cooling_switch_specs({"PresentationType": node}) == []


def test_min_max_step_node_is_a_number():
    node = {"Value": 2, "Min": 1, "Max": 3, "Step": 1}
    assert discovery.classify_node("HumidityControl", node) == "number"


def test_bounds_without_step_still_classify_as_number():
    # number.py defaults Step, so Min/Max alone is a usable range.
    assert discovery.classify_node("SomeLevel", {"Value": 2, "Min": 0, "Max": 7}) == "number"


def test_enumerated_values_win_over_bounds():
    # A node that reports both is a choice; the enumeration is the more specific fact.
    node = {"Value": 1, "AllValues": [1, 2], "Min": 1, "Max": 2, "Step": 1}
    assert discovery.classify_node("AirFilter", node) == "toggle"


def test_non_conventional_pair_is_skipped_not_guessed():
    # {0, 1} is not Miele's 1=on/2=off convention; writing a guess to a real
    # appliance is worse than exposing nothing.
    node = {"Value": 0, "AllValues": [0, 1]}
    assert discovery.toggle_values(node) is None
    assert discovery.classify_node("MysteryFlag", node) is None
    assert discovery.cooling_switch_specs({"MysteryFlag": node}) == []


@pytest.mark.parametrize(
    "node",
    [
        {"Value": 2},                                  # AllValues missing
        {"Value": 2, "AllValues": []},                 # empty
        {"Value": 2, "AllValues": {}},                 # non-list
        {"Value": 2, "AllValues": "12"},               # string
        {"Value": 2, "AllValues": ["1", "2"]},         # strings inside
        {"Value": 2, "AllValues": [True, False]},      # bools are not values
        {"Value": 2, "AllValues": [1]},                # single value
        {"Value": 2, "AllValues": [[1], [2]]},         # nested lists
        {"Value": 2, "AllValues": None},
    ],
)
def test_malformed_nodes_are_skipped_not_raised(node):
    assert discovery.toggle_values(node) is None
    assert discovery.classify_node("Unheard", node) is None
    assert discovery.cooling_switch_specs({"Unheard": node}) == []
    assert list(discovery.iter_cooling_nodes({"Unheard": node})) == []


@pytest.mark.parametrize("cooling", [None, {}, [], "nope", 42, {"Sabbath": None}, {"Sabbath": "on"}])
def test_malformed_payloads_yield_nothing(cooling):
    assert list(discovery.iter_cooling_nodes(cooling)) == []
    assert discovery.cooling_switch_specs(cooling) == []


def test_zone_keys_are_skipped():
    names = [name for name, _node, _kind in discovery.iter_cooling_nodes(COOLING)]
    assert "0" not in names and "1" not in names
    assert {"Sabbath", "ChildProof", "AirFilter"} <= set(names)


def test_iter_cooling_nodes_reports_kinds():
    kinds = {name: kind for name, _node, kind in discovery.iter_cooling_nodes(COOLING)}
    assert kinds == {
        "Sabbath": "toggle",
        "ChildProof": "toggle",
        "AirFilter": "toggle",
        "PresentationLight": "toggle",
        "HumidityControl": "number",
    }


def test_switch_specs_match_the_three_shipped_switches():
    specs = discovery.cooling_switch_specs(COOLING)
    assert [(s.name, s.friendly, s.on_value, s.off_value) for s in specs] == [
        ("AirFilter", "Active air filter", 1, 2),
        ("ChildProof", "Child lock", 1, 2),
        ("Sabbath", "Sabbath mode", 1, 2),
    ]


def test_unique_id_key_format_is_unchanged():
    # entity.py builds unique_id as f"{mac}_{key}". These three keys are the
    # contract with every existing installation — changing one orphans entities.
    keys = {s.name: s.key for s in discovery.cooling_switch_specs(COOLING)}
    assert keys == {
        "Sabbath": "cooling_sabbath",
        "ChildProof": "cooling_childproof",
        "AirFilter": "cooling_airfilter",
    }


def test_platform_owned_names_are_not_switches():
    names = [s.name for s in discovery.cooling_switch_specs(COOLING)]
    assert "PresentationLight" not in names   # light platform
    assert "HumidityControl" not in names     # number platform


@pytest.mark.parametrize("name", ["TempUnit", "PresentationType"])
def test_enumerations_get_no_switch_even_at_two_values(name):
    # These are enumerations, not toggles, and belong to a future select platform.
    # The node shape alone cannot tell them apart from a real toggle, which is
    # exactly why the exclusion is by name — see NOT_SWITCHES.
    assert discovery.cooling_switch_specs({name: TOGGLE_NODE}) == []
    # ...while an identically-shaped Sabbath node still produces its switch. This
    # contrast is the regression guard: it fails if the exclusion is dropped.
    specs = discovery.cooling_switch_specs({"Sabbath": TOGGLE_NODE})
    assert [(s.name, s.key) for s in specs] == [("Sabbath", "cooling_sabbath")]


def test_excluded_enumerations_are_still_visible_to_other_platforms():
    # Excluded from switches, not from discovery — a select platform must be able
    # to find them without re-walking the payload.
    kinds = {
        name: kind
        for name, _node, kind in discovery.iter_cooling_nodes(
            {
                "TempUnit": {"Value": 1, "AllValues": [1, 2]},
                "PresentationType": {"Value": 1, "AllValues": [1, 2, 3]},
            }
        )
    }
    assert kinds == {"TempUnit": "toggle", "PresentationType": "select"}


def test_known_toggle_without_enumeration_keeps_its_switch():
    # Defensive: a firmware that omits AllValues on a node we have always shipped
    # must not make that entity vanish on upgrade.
    specs = discovery.cooling_switch_specs({"Sabbath": {"Value": 2}})
    assert [(s.name, s.on_value, s.off_value, s.key) for s in specs] == [
        ("Sabbath", 1, 2, "cooling_sabbath")
    ]


def test_unmet_two_valued_node_becomes_a_switch():
    # The point of the whole module: a field from another cooling appliance that
    # nobody enumerated still gets an entity.
    specs = discovery.cooling_switch_specs({"SuperCooling": TOGGLE_NODE})
    assert [(s.name, s.friendly, s.key) for s in specs] == [
        ("SuperCooling", "Super cooling", "cooling_supercooling")
    ]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Sabbath", "Sabbath mode"),
        ("ChildProof", "Child lock"),
        ("AirFilter", "Active air filter"),
        ("PresentationLight", "Presentation light"),
        ("PresentationType", "Presentation type"),
        ("TempUnit", "Temperature unit"),
        ("HumidityControl", "Humidity level"),
        ("SuperCooling", "Super cooling"),
        ("SuperFreezing", "Super freezing"),
        ("ECOMode", "ECO mode"),
        ("Zone2Boost", "Zone 2 boost"),
        ("lowercase", "Lowercase"),
        ("", ""),
    ],
)
def test_friendly_name(name, expected):
    assert discovery.friendly_name(name) == expected
