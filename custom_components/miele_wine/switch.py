"""Toggleable /Cooling/{name} settings as switches.

Which switches exist is discovered from the payload, not hardcoded: each node
reports its own legal values, so any two-valued /Cooling/ field the appliance
offers becomes a switch — including fields on cooling appliances this integration
has never been run against. See discovery.py for the classification rules.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .discovery import CoolingSwitchSpec, cooling_switch_specs
from .entity import MieleWineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Only what this appliance actually reports — the payload is the source of truth.
    entities = [
        MieleCoolingSwitch(coordinator, spec)
        for spec in cooling_switch_specs(coordinator.data.get("cooling", {}))
    ]
    async_add_entities(entities)


class MieleCoolingSwitch(MieleWineEntity, SwitchEntity):
    """A /Cooling/{name} on/off setting."""

    def __init__(self, coordinator, spec: CoolingSwitchSpec) -> None:
        # spec.key is f"cooling_{name.lower()}" — the unique_id format shipped
        # since the first release. Do not change it; it would orphan the entity.
        super().__init__(coordinator, spec.key)
        self._name = spec.name
        self._on_value = spec.on_value
        self._off_value = spec.off_value
        self._attr_name = spec.friendly

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
