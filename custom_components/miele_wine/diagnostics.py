"""Diagnostics for the Miele Wine integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MAC, CONF_TOKENS, DOMAIN

TO_REDACT = {
    CONF_TOKENS,
    CONF_MAC,
    "access_token",
    "refresh_token",
    "id_token",
    "mac",
    "groupId",
    "groupKey",
    "sub",
    "FabNumber",
    # ident.py resolves the serial under either spelling, so both have to be
    # redacted; "serial" is the field name this integration uses downstream.
    "fabNumber",
    "serial",
    "serial_number",
    "serialNo",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "ident": async_redact_data(coordinator.ident, TO_REDACT),
        "state": async_redact_data(coordinator.data, TO_REDACT),
    }
