"""Unit tests for the write-result checker and the centi-°C conversions.

No network and no Home Assistant: conftest.py puts the component directory on
sys.path so `api` imports standalone. The entity classes can't be tested here (they
import homeassistant, which CI does not install).
"""
import pytest

import api


def test_success_passes_through():
    result = [{"Success": {"Value": 1}}]
    assert api.check_write_result(result) is result


def test_failure_raises():
    with pytest.raises(api.MieleApiError):
        api.check_write_result([{"Failure": {"Value": None}}])


def test_mixed_raises():
    with pytest.raises(api.MieleApiError):
        api.check_write_result([{"Success": {"Value": 1}}, {"Failure": {"x": None}}])


def test_empty_ok():
    assert api.check_write_result(None) is None
    assert api.check_write_result([]) == []


# --- temperature conversions -------------------------------------------------

@pytest.mark.parametrize("centi,celsius", [
    (1200, 12.0),
    (500, 5.0),
    (1250, 12.5),
    (0, 0.0),
    (-1850, -18.5),      # freezer-range zones are negative on the wire
    (-50, -0.5),
])
def test_centi_to_celsius(centi, celsius):
    assert api.centi_to_celsius(centi) == celsius


def test_centi_to_celsius_missing_is_none():
    assert api.centi_to_celsius(None) is None


def test_centi_to_celsius_unused_sentinel_is_none():
    # -32768 means "zone/sensor not in use", not -327.68 °C.
    assert api.centi_to_celsius(api.UNUSED_TEMP) is None


@pytest.mark.parametrize("celsius,centi", [
    (12.0, 1200),
    (5, 500),
    (12.5, 1250),
    (0, 0),
    (-18.5, -1850),
])
def test_celsius_to_centi(celsius, centi):
    assert api.celsius_to_centi(celsius) == centi


@pytest.mark.parametrize("centi", [500, 1200, 1250, 1425, -1850, 0])
def test_round_trip(centi):
    assert api.celsius_to_centi(api.centi_to_celsius(centi)) == centi


@pytest.mark.parametrize("celsius,centi", [
    (12.125, 1212),      # exact .5 centi -> Python rounds halves to even
    (12.135, 1214),      # 1213.5 is not exact in binary; it lands above the half
    (12.5, 1250),        # a half degree is exact and unambiguous
    (-12.125, -1212),
])
def test_celsius_to_centi_half_values(celsius, centi):
    """Pin the documented rounding. The appliance's Step is whole degrees, so these
    only arise from hand-written service calls; it rejects off-step values itself."""
    assert api.celsius_to_centi(celsius) == centi
