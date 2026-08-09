"""The Miele Wine (consumer cloud) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MieleCloud
from .const import CONF_MAC, CONF_TOKENS, DOMAIN, PLATFORMS
from .coordinator import MieleWineCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    session = async_get_clientsession(hass)

    async def _persist_tokens(tokens: dict[str, Any]) -> None:
        # The client rotated tokens; save them back to the entry so refresh survives restart.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_TOKENS: tokens}
        )

    client = MieleCloud(session, entry.data[CONF_TOKENS], on_tokens=_persist_tokens)
    coordinator = MieleWineCoordinator(hass, entry, client, entry.data[CONF_MAC])
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
