"""Presentation light (on/off) — PUT /Cooling/PresentationLight {"Value":1|2}."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import LIGHT_ON
from .const import DOMAIN
from .entity import MieleWineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MielePresentationLight(coordinator)])


class MielePresentationLight(MieleWineEntity, LightEntity):
    """The wine cabinet presentation light."""

    _attr_translation_key = "presentation_light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "presentation_light")

    @property
    def is_on(self) -> bool | None:
        pl = self.coordinator.data.get("cooling", {}).get("PresentationLight")
        if not pl:
            return None
        return pl.get("Value") == LIGHT_ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_presentation_light(self.coordinator.mac, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_presentation_light(self.coordinator.mac, False)
        await self.coordinator.async_request_refresh()
