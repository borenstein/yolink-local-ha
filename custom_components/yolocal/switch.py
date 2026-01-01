"""Switch platform for YoLink Local integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from yolocal.const import DOMAIN
from yolocal.coordinator import YoLocalCoordinator
from yolocal.entity import YoLocalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up YoLink switches from a config entry."""
    coordinator: YoLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = []
    for device in coordinator.devices.values():
        if device.device_type == "Outlet":
            entities.append(YoLocalSwitch(coordinator, device))

    async_add_entities(entities)


class YoLocalSwitch(YoLocalEntity, SwitchEntity):
    """Switch entity for YoLink outlet."""

    _attr_device_class = SwitchDeviceClass.OUTLET
    _attr_name = None  # Use device name

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        state = self.device_state.get("state")
        if state is None:
            return None
        # YoLink uses "open" for on, "closed" for off (relay terminology)
        return state == "open"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.coordinator.async_send_command(
            self._device.device_id,
            {"state": "open"},
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.coordinator.async_send_command(
            self._device.device_id,
            {"state": "closed"},
        )

