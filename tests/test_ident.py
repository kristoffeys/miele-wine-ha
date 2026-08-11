"""Unit tests for the /Ident/ parser (no network, no Home Assistant)."""
import pytest

import ident

MAC = "000707396550"

# Shape observed on this unit (KWTUS 7096 E, XKM EK057LHBM, firmware 33.22).
# The XKM block's key name is not confirmed on the cloud payload, hence the
# tolerance tests below.
FULL = {
    "DeviceName": "Wijnkast",
    "DeviceIdentLabel": {
        "FabNumber": "000707396550",
        "FabIndex": "22",
        "TechType": "KWTUS 7096 E",
        "MatNumber": "11117740",
    },
    "XkmIdentLabel": {
        "TechType": "EK057LHBM",
        "ReleaseVersion": "33.22",
    },
}


def test_full_payload_parses_every_field():
    parsed = ident.parse_ident(FULL)
    assert parsed.model == "KWTUS 7096 E"
    assert parsed.serial == "000707396550"
    assert parsed.hw_version == "EK057LHBM"
    assert parsed.sw_version == "33.22"
    # No Brand key in the payload; the manufacturer default is applied by
    # with_defaults(), not by the parser.
    assert parsed.manufacturer is None


def test_camel_case_spellings_parse():
    parsed = ident.parse_ident(
        {
            "deviceIdentLabel": {"techType": "KWTUS 7096 E", "fabNumber": "123"},
            "xkmIdentLabel": {"techType": "EK057LHBM", "releaseVersion": "33.22"},
        }
    )
    assert (parsed.model, parsed.serial) == ("KWTUS 7096 E", "123")
    assert (parsed.hw_version, parsed.sw_version) == ("EK057LHBM", "33.22")


def test_partial_payload_falls_back_per_field():
    # Model present, XKM block absent: we keep the model and lose only the
    # firmware/hardware strings.
    parsed = ident.parse_ident({"DeviceIdentLabel": {"TechType": "KWTUS 7096 E"}})
    assert parsed.model == "KWTUS 7096 E"
    assert parsed.serial is None
    assert parsed.sw_version is None
    assert parsed.hw_version is None

    # XKM block present, appliance label absent: the reverse.
    parsed = ident.parse_ident({"XkmIdentLabel": {"ReleaseVersion": "33.22"}})
    assert parsed.model is None
    assert parsed.sw_version == "33.22"
    assert parsed.hw_version is None


def test_flattened_root_names_parse():
    # /V2/Devices/{mac}/ has been seen carrying these names one level up.
    parsed = ident.parse_ident({"TechType": "KWTUS 7096 E", "FabNumber": "123"})
    assert (parsed.model, parsed.serial) == ("KWTUS 7096 E", "123")
    # A root TechType is the appliance, never the WiFi module.
    assert parsed.hw_version is None


@pytest.mark.parametrize("payload", [None, {}, {"DeviceIdentLabel": {}}])
def test_empty_payloads_give_all_none(payload):
    parsed = ident.parse_ident(payload)
    assert parsed == ident.DeviceIdent()


@pytest.mark.parametrize(
    "payload",
    [
        "not a dict",
        [],
        [{"DeviceIdentLabel": {"TechType": "x"}}],
        42,
        {"DeviceIdentLabel": "a string where a dict belongs"},
        {"DeviceIdentLabel": ["a", "list"]},
        {"DeviceIdentLabel": None},
        {"DeviceIdentLabel": {"TechType": {"unexpected": {"extra": "level"}}}},
        {"DeviceIdentLabel": {"TechType": True}},
        {"XkmIdentLabel": {"ReleaseVersion": {"deeper": ["nope"]}}},
    ],
)
def test_unexpected_shapes_do_not_raise(payload):
    parsed = ident.parse_ident(payload)
    assert isinstance(parsed, ident.DeviceIdent)
    # Whatever the shape, the fallbacks still produce a usable device page.
    assert parsed.with_defaults(MAC).model == ident.DEFAULT_MODEL


def test_value_wrapped_fields_are_unwrapped():
    # The 3rd-party API shape: {"value_raw": …, "value_localized": …}.
    parsed = ident.parse_ident(
        {
            "DeviceIdentLabel": {
                "TechType": {"value_raw": 19, "value_localized": "KWTUS 7096 E"},
                "FabNumber": {"value_localized": "000707396550"},
            },
            "XkmIdentLabel": {"ReleaseVersion": {"value_raw": 33.22}},
        }
    )
    assert parsed.model == "KWTUS 7096 E"
    assert parsed.serial == "000707396550"
    assert parsed.sw_version == "33.22"


def test_blank_strings_are_treated_as_absent():
    parsed = ident.parse_ident(
        {"DeviceIdentLabel": {"TechType": "   ", "FabNumber": ""}}
    )
    assert parsed.model is None
    assert parsed.serial is None
    assert parsed.with_defaults(MAC).model == ident.DEFAULT_MODEL


def test_model_fallback_and_serial_falls_back_to_mac():
    info = ident.device_ident({}, MAC)
    assert info.model == "Wine conditioning unit"
    assert info.model == ident.DEFAULT_MODEL
    # Pre-existing behaviour: no FabNumber means the serial stays the mac.
    assert info.serial == MAC
    assert info.manufacturer == "Miele"
    assert info.sw_version is None
    assert info.hw_version is None


def test_device_ident_prefers_reported_values_over_fallbacks():
    info = ident.device_ident(FULL, MAC)
    assert info.model == "KWTUS 7096 E"
    assert info.serial == "000707396550"
    assert info.sw_version == "33.22"
    assert info.hw_version == "EK057LHBM"
    assert info.manufacturer == "Miele"


def test_reported_brand_wins_over_the_manufacturer_default():
    info = ident.device_ident({"Brand": "Miele & Cie."}, MAC)
    assert info.manufacturer == "Miele & Cie."
