"""Unit tests for the write-result checker (no network, no Home Assistant)."""
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
