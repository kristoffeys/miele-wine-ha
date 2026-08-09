"""Polling coordinator: fetches /Cooling/ and both zones each interval."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MieleApiError, MieleAuthError, MieleCloud
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class MieleWineCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches the appliance's cooling state on an interval."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: MieleCloud, mac: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.mac = mac
        self.entry = entry
        self.ident: dict[str, Any] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            if not self.ident:
                try:
                    self.ident = await self.client.get_ident(self.mac)
                except MieleApiError:
                    self.ident = {}
            cooling = await self.client.get_cooling(self.mac)
            zones: dict[str, Any] = {}
            for z in [k for k in cooling if k.isdigit()]:
                zones[z] = await self.client.get_zone(self.mac, z)
            return {"cooling": cooling, "zones": zones}
        except MieleAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MieleApiError as err:
            raise UpdateFailed(str(err)) from err
