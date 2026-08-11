"""Services exposing api.py's generic /Cooling setters to users and automations.

Thin wrappers over PUT /V2/Devices/{mac}/Cooling/{name} and /Cooling/{zone}/{name} —
the only write path this appliance's firmware permits (local /State, cloud /State and
DOP2 writes are all gated; see FINDINGS.md). They exist as an escape hatch: the traffic
capture never enumerated the full /Cooling/ body, so a user can poke a node this
integration has no entity for from Developer Tools instead of waiting for a release.

The services return the appliance's raw write response, which is what makes them useful
for discovery: a node that exists answers [{"Success":{"Value":N}}], one that does not
fails loudly.

Argument checking lives in validate.py, which imports no homeassistant so CI can
unit-test the path-traversal guard on `name`/`zone` without Home Assistant installed.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .api import MieleApiError, MieleAuthError
from .const import DOMAIN
from .coordinator import MieleWineCoordinator
from .validate import (
    InvalidServiceData,
    validate_node_name,
    validate_value,
    validate_zone,
)

SERVICE_SET_COOLING_VALUE = "set_cooling_value"
SERVICE_SET_ZONE_VALUE = "set_zone_value"

ATTR_DEVICE_ID = "device_id"
ATTR_ENTRY_ID = "entry_id"
ATTR_NAME = "name"
ATTR_VALUE = "value"
ATTR_ZONE = "zone"


def _vol_check(validator: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Reuse a validate.py checker as a voluptuous validator.

    voluptuous flattens a bare ValueError into "not a valid value", which throws away
    the reason. Re-raising as vol.Invalid keeps our message, so the schema and the
    handler enforce one implementation of the rules on two surfaces.
    """

    def _check(value: Any) -> Any:
        try:
            return validator(value)
        except InvalidServiceData as err:
            raise vol.Invalid(str(err)) from err

    return _check


# Exclusive: naming both a device and a config entry is a contradiction, not a merge.
_TARGET_FIELDS = {
    vol.Exclusive(ATTR_DEVICE_ID, "target"): cv.string,
    vol.Exclusive(ATTR_ENTRY_ID, "target"): cv.string,
}

SET_COOLING_VALUE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_NAME): _vol_check(validate_node_name),
        vol.Required(ATTR_VALUE): _vol_check(validate_value),
        **_TARGET_FIELDS,
    }
)

SET_ZONE_VALUE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ZONE): _vol_check(validate_zone),
        vol.Required(ATTR_NAME): _vol_check(validate_node_name),
        vol.Required(ATTR_VALUE): _vol_check(validate_value),
        **_TARGET_FIELDS,
    }
)


def _checked(validator: Callable[[Any], Any], value: Any) -> Any:
    """Run a validate.py checker inside a handler, as user-facing validation."""
    try:
        return validator(value)
    except InvalidServiceData as err:
        raise ServiceValidationError(str(err)) from err


def _resolve_coordinator(hass: HomeAssistant, data: dict[str, Any]) -> MieleWineCoordinator:
    """Pick the coordinator this call targets.

    hass.data[DOMAIN] only holds entries that are currently loaded (see __init__.py), so
    membership in it doubles as the "is this target usable" test.
    """
    loaded: dict[str, MieleWineCoordinator] = hass.data.get(DOMAIN, {})
    if not loaded:
        raise ServiceValidationError("No loaded Miele wine cabinet config entry")

    if device_id := data.get(ATTR_DEVICE_ID):
        device = dr.async_get(hass).async_get(device_id)
        if device is None:
            raise ServiceValidationError(f"Unknown device_id {device_id!r}")
        # A device can in principle belong to several entries; take the first loaded one.
        entry_ids = [eid for eid in device.config_entries if eid in loaded]
        if not entry_ids:
            raise ServiceValidationError(
                f"Device {device_id!r} does not belong to a loaded {DOMAIN} config entry"
            )
        return loaded[entry_ids[0]]

    if entry_id := data.get(ATTR_ENTRY_ID):
        if entry_id not in loaded:
            raise ServiceValidationError(
                f"No loaded {DOMAIN} config entry with entry_id {entry_id!r}"
            )
        return loaded[entry_id]

    if len(loaded) > 1:
        raise ServiceValidationError(
            "Several Miele wine cabinets are set up; name one with device_id or entry_id"
        )
    return next(iter(loaded.values()))


async def _write(
    coordinator: MieleWineCoordinator, path: str, do_write: Awaitable[Any]
) -> ServiceResponse:
    """Await a write, translate client errors, then refresh so the UI catches up."""
    try:
        result = await do_write
    except MieleAuthError as err:
        raise HomeAssistantError(
            f"Miele authentication failed writing {path}: {err}"
        ) from err
    except MieleApiError as err:
        # Covers the 200 + [{"Failure": {...}}] envelope that api.check_write_result
        # turns into an error: a value the appliance refused must not read as success.
        raise HomeAssistantError(f"Miele write to {path} failed: {err}") from err
    await coordinator.async_request_refresh()
    return {"result": result}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services once, however many config entries load."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_COOLING_VALUE):
        return

    async def _async_set_cooling_value(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call.data)
        # Re-check here rather than trust the schema: this is the guard that keeps the
        # value out of the URL path, and a guard that only lives in the schema is one
        # schema edit away from being gone.
        name = _checked(validate_node_name, call.data[ATTR_NAME])
        value = _checked(validate_value, call.data[ATTR_VALUE])
        return await _write(
            coordinator,
            f"/Cooling/{name}",
            coordinator.client.set_cooling_value(coordinator.mac, name, value),
        )

    async def _async_set_zone_value(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call.data)
        zone = _checked(validate_zone, call.data[ATTR_ZONE])
        name = _checked(validate_node_name, call.data[ATTR_NAME])
        value = _checked(validate_value, call.data[ATTR_VALUE])
        return await _write(
            coordinator,
            f"/Cooling/{zone}/{name}",
            coordinator.client.set_zone_value(coordinator.mac, zone, name, value),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_COOLING_VALUE,
        _async_set_cooling_value,
        schema=SET_COOLING_VALUE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ZONE_VALUE,
        _async_set_zone_value,
        schema=SET_ZONE_VALUE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


@callback
def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the services — called when the last config entry unloads."""
    for service in (SERVICE_SET_COOLING_VALUE, SERVICE_SET_ZONE_VALUE):
        hass.services.async_remove(DOMAIN, service)
