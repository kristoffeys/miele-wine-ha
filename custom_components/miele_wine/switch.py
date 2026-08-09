"""Toggleable /Cooling/ settings as switches (Sabbath, Child lock, Air filter)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COOLING_SWITCHES, DOMAIN
from .entity import MieleWineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    cooling = coordinator.data.get("cooling", {})
    entities = [
        MieleCoolingSwitch(coordinator, name, *cfg)
        for name, cfg in COOLING_SWITCHES.items()
        if name in cooling  # only expose what the appliance reports
    ]
    async_add_entities(entities)


class MieleCoolingSwitch(MieleWineEntity, SwitchEntity):
    """A /Cooling/{name} on/off setting."""

    def __init__(self, coordinator, name: str, friendly: str, on_value: int, off_value: int) -> None:
        super().__init__(coordinator, f"cooling_{name.lower()}")
        self._name = name
        self._on_value = on_value
        self._off_value = off_value
        self._attr_name = friendly

    @property
    def is_on(self) -> bool | None:
        node = self.coordinator.data.get("cooling", {}).get(self._name)
        if not node:
            return None
        return node.get("Value") == self._on_value

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_cooling_value(self.coordinator.mac, self._name, self._on_value)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_cooling_value(self.coordinator.mac, self._name, self._off_value)
        await self.coordinator.async_request_refresh()
