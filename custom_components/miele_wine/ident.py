"""Parsing of GET /V2/Devices/{mac}/Ident/ into device identity fields.

The coordinator already fetches this endpoint once per config entry; this module
turns the payload into the handful of strings Home Assistant's device registry
wants (model, serial, firmware, hardware). Surfacing the XKM module type and its
release version matters for support: on this appliance family every write path is
firmware-gated, so "which firmware" is the first question any bug report raises.

Deliberately Home-Assistant-free — tests/conftest.py puts this package on
sys.path and imports the module standalone, so it must not import homeassistant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Displayed when the appliance reports no TechType. Preserves the label this
# integration has always shown rather than degrading to "Unknown".
DEFAULT_MODEL = "Wine conditioning unit"

MANUFACTURER = "Miele"

# Miele nests the appliance's own label under DeviceIdentLabel (observed on
# rest-eu.domestic for this unit) and the WiFi module's under XkmIdentLabel
# (observed on the local gateway API; the cloud key name for the XKM block is
# NOT confirmed on this firmware). Both PascalCase and camelCase spellings are
# in circulation across firmware/API generations, so every lookup tries both and
# an unknown spelling simply yields None instead of an error.
_DEVICE_LABEL_KEYS = ("DeviceIdentLabel", "deviceIdentLabel")
_XKM_LABEL_KEYS = ("XkmIdentLabel", "xkmIdentLabel", "XkmIdent", "xkmIdent")

_TECH_TYPE_KEYS = ("TechType", "techType")
_FAB_NUMBER_KEYS = ("FabNumber", "fabNumber")
# The XKM firmware string ("33.22" on this unit). Different generations label it
# ReleaseVersion / SwVersion / VersionString.
_RELEASE_KEYS = (
    "ReleaseVersion",
    "releaseVersion",
    "SwVersion",
    "swVersion",
    "VersionString",
    "versionString",
)

# Miele's 3rd-party API wraps scalars as {"value_raw": …, "value_localized": …}
# while the domestic API returns them bare. Accept either so a firmware that
# switches shapes does not blank out the device page.
_VALUE_KEYS = ("value_localized", "valueLocalized", "value_raw", "Value", "value")


@dataclass(frozen=True)
class DeviceIdent:
    """Identity of the appliance; every field is independently optional."""

    model: str | None = None
    serial: str | None = None
    sw_version: str | None = None
    hw_version: str | None = None
    manufacturer: str | None = None

    def with_defaults(self, mac: str) -> DeviceIdent:
        """Same identity with this integration's display fallbacks applied.

        `serial` falls back to the mac because that is what the device registry
        has shown since the first release — changing it would rewrite the serial
        of every already-registered device.
        """
        return DeviceIdent(
            model=self.model or DEFAULT_MODEL,
            serial=self.serial or mac,
            sw_version=self.sw_version,
            hw_version=self.hw_version,
            manufacturer=self.manufacturer or MANUFACTURER,
        )


def _as_mapping(value: Any) -> dict[str, Any]:
    """Return `value` when it is a mapping, else {}.

    Guards the nesting assumptions: a firmware handing back a string or a list
    where a label object is expected must not raise on `.get()`.
    """
    return value if isinstance(value, dict) else {}


def _coerce_str(value: Any) -> str | None:
    """Best-effort flatten of one Ident field to a non-empty display string.

    Handles the bare scalar, the {"value_raw": …} wrapper and the single-element
    list some builds return. Numbers are stringified because a firmware version
    occasionally arrives as a number rather than a string. Booleans and anything
    unrecognised yield None — never an exception.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in _VALUE_KEYS:
            if key in value:
                nested = _coerce_str(value[key])
                if nested is not None:
                    return nested
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            nested = _coerce_str(item)
            if nested is not None:
                return nested
    return None


def _first(source: Any, keys: tuple[str, ...]) -> str | None:
    """First key in `keys` that yields a usable string on `source`."""
    mapping = _as_mapping(source)
    for key in keys:
        coerced = _coerce_str(mapping.get(key))
        if coerced is not None:
            return coerced
    return None


def _nested(root: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """The first label block found under `keys`, as a mapping."""
    for key in keys:
        if key in root:
            return _as_mapping(root[key])
    return {}


def parse_ident(ident: dict[str, Any] | None) -> DeviceIdent:
    """Extract the device identity from an /Ident/ payload.

    Never raises: an unparseable or unexpectedly shaped payload gives a
    DeviceIdent whose fields are None, and each field is resolved independently
    so a missing XKM block does not cost us the model (or vice versa).
    """
    root = _as_mapping(ident)
    device = _nested(root, _DEVICE_LABEL_KEYS)
    xkm = _nested(root, _XKM_LABEL_KEYS)

    return DeviceIdent(
        # The root fallbacks cover /V2/Devices/{mac}/, which has been seen
        # flattening these same names one level up.
        model=_first(device, _TECH_TYPE_KEYS) or _first(root, _TECH_TYPE_KEYS),
        serial=_first(device, _FAB_NUMBER_KEYS) or _first(root, _FAB_NUMBER_KEYS),
        sw_version=(
            _first(xkm, _RELEASE_KEYS)
            or _first(device, _RELEASE_KEYS)
            or _first(root, _RELEASE_KEYS)
        ),
        # hw_version is the WiFi module type (EK057LHBM on this unit) and has no
        # root fallback: a bare root TechType is the appliance, not the module,
        # and reporting it as hardware would be actively misleading.
        hw_version=_first(xkm, _TECH_TYPE_KEYS),
        manufacturer=_first(root, ("Brand", "brand")) or None,
    )


def device_ident(ident: dict[str, Any] | None, mac: str) -> DeviceIdent:
    """Parsed identity with display fallbacks — what the entity layer wants."""
    return parse_ident(ident).with_defaults(mac)
