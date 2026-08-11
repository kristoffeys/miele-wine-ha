"""Unit tests for the service argument validators (no network, no Home Assistant).

The `name` and `zone` checks are the path-traversal guard for the URL these services
build, so the rejection cases below are the point of the module, not edge-case padding.
"""
import pytest

import validate


@pytest.mark.parametrize(
    "name",
    ["Sabbath", "PresentationLight", "HumidityControl", "A", "Zone2Temp", "a"],
)
def test_valid_node_names(name):
    assert validate.validate_node_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",           # empty would PUT /Cooling/ itself
        "a/b",        # a slash addresses a different resource
        "../x",       # climbs out of /Cooling/
        "..",
        "a.b",
        "1abc",       # API node names never start with a digit
        "Sabbath\n",  # a "^...$" pattern would let this through
        "Sabbath ",
        "Sab bath",
        "Sabbath%2Fx",
        "Sabbath?x=1",
    ],
)
def test_invalid_node_names(name):
    with pytest.raises(validate.InvalidServiceData):
        validate.validate_node_name(name)


@pytest.mark.parametrize("name", [None, 1, True, ["Sabbath"]])
def test_node_name_must_be_a_string(name):
    with pytest.raises(validate.InvalidServiceData):
        validate.validate_node_name(name)


@pytest.mark.parametrize("zone,expected", [("1", "1"), ("2", "2"), ("10", "10"), (1, "1")])
def test_valid_zones(zone, expected):
    assert validate.validate_zone(zone) == expected


@pytest.mark.parametrize("zone", ["a", "", "1/2", "../1", "1.0", "-1", "1\n", True, None, 1.0])
def test_invalid_zones(zone):
    with pytest.raises(validate.InvalidServiceData):
        validate.validate_zone(zone)


@pytest.mark.parametrize("value", [1, 0, -1, 1200, -32768])
def test_valid_values(value):
    assert validate.validate_value(value) == value


@pytest.mark.parametrize("value", [True, False, 1.5, 1.0, "1", None, [1]])
def test_invalid_values(value):
    with pytest.raises(validate.InvalidServiceData):
        validate.validate_value(value)
