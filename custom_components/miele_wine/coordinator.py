"""Polling coordinator: fetches /Cooling/ and both zones each interval."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MieleApiError, MieleAuthError, MieleCloud
from .const import (
    CONF_ADAPTIVE,
    CONF_SCAN_INTERVAL,
    DEFAULT_ADAPTIVE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .polling import any_door_open, next_interval

_LOGGER = logging.getLogger(__name__)


class MieleWineCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches the appliance's cooling state on an interval."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: MieleCloud, mac: str) -> None:
        # Options are absent on entries created before the options flow existed, so the
        # defaults here are the historical hardcoded behaviour.
        base_interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=base_interval),
        )
        self.client = client
        self.mac = mac
        self.entry = entry
        self.ident: dict[str, Any] = {}
        self.base_interval = base_interval
        self.adaptive = bool(entry.options.get(CONF_ADAPTIVE, DEFAULT_ADAPTIVE))
        self.consecutive_errors = 0
        # time.monotonic(), not wall clock: only elapsed time matters and it must survive
        # a clock step. None until the first write of this HA run.
        self._last_write: float | None = None

    def note_write(self) -> None:
        """Record that a write to the appliance just succeeded.

        The cabinet needs a few seconds before GET /Cooling/ reflects a PUT, so this
        opens a short fast-poll window and the UI stops lagging behind a toggle.
        """
        self._last_write = time.monotonic()

    async def async_request_refresh(self) -> None:
        """Refresh sooner than the schedule; also treated as "a write just happened".

        Every entity write path calls this immediately after its PUT, so recording the
        write timestamp here covers all platforms without editing each of them.
        """
        self.note_write()
        await super().async_request_refresh()

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
            data = {"cooling": cooling, "zones": zones}
        except MieleAuthError as err:
            # Reauth takes over from here; don't count it as a transport failure.
            raise ConfigEntryAuthFailed(str(err)) from err
        except MieleApiError as err:
            self.consecutive_errors += 1
            # Keep the last known zones: only the error count matters while backing off.
            self._apply_interval(self.data)
            raise UpdateFailed(str(err)) from err

        self.consecutive_errors = 0
        self._apply_interval(data)
        return data

    def _apply_interval(self, data: dict[str, Any] | None) -> None:
        """Re-evaluate the poll interval from what the last refresh told us."""
        seconds_since_write = (
            None if self._last_write is None else time.monotonic() - self._last_write
        )
        seconds = next_interval(
            self.base_interval,
            adaptive=self.adaptive,
            door_open=any_door_open((data or {}).get("zones")),
            seconds_since_write=seconds_since_write,
            consecutive_errors=self.consecutive_errors,
        )
        if self.update_interval != timedelta(seconds=seconds):
            self.update_interval = timedelta(seconds=seconds)
