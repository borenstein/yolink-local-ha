"""Switch platform for YoLink Local integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import YoLocalCoordinator
from .entity import YoLocalEntity


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
        elif device.device_type == "MultiOutlet":
            for channel in _multioutlet_channels(coordinator.get_state(device.device_id)):
                entities.append(YoLocalMultiOutletSwitch(coordinator, device, channel))

    async_add_entities(entities)


def _multioutlet_channels(state: dict[str, Any]) -> list[int]:
    """Return the real socket channel indices for a MultiOutlet device.

    YoLink pads the ``state`` list to a fixed length (8) regardless of the
    physical socket count, so we use the ``delays`` array — which only contains
    an entry per real socket — to decide how many switch entities to create.
    """
    delays = state.get("delays")
    if isinstance(delays, list):
        channels = sorted(
            entry["ch"]
            for entry in delays
            if isinstance(entry, dict) and isinstance(entry.get("ch"), int)
        )
        if channels:
            return channels
    return [0]


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
        # getState reports "open" (on) / "closed" (off) in relay terminology.
        return state == "open"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.coordinator.async_send_command(
            self._device.device_id,
            {"state": "open"},
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        # setState uses the verb form "close" (getState reports "closed").
        await self.coordinator.async_send_command(
            self._device.device_id,
            {"state": "close"},
        )


class YoLocalMultiOutletSwitch(YoLocalEntity, SwitchEntity):
    """Switch entity for a single socket of a YoLink MultiOutlet."""

    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, coordinator: YoLocalCoordinator, device, channel: int) -> None:
        """Initialize the socket switch."""
        super().__init__(coordinator, device)
        self._channel = channel
        self._chs_mask = 1 << channel
        self._attr_unique_id = f"{device.device_id}_ch{channel}"
        self._attr_name = f"Socket {channel + 1}"

    @property
    def is_on(self) -> bool | None:
        """Return True if this socket is on."""
        channels = self.device_state.get("state")
        if not isinstance(channels, list) or self._channel >= len(channels):
            return None
        return channels[self._channel] == "open"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn this socket on."""
        await self.coordinator.async_send_command(
            self._device.device_id,
            {"chs": self._chs_mask, "state": "open"},
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn this socket off."""
        await self.coordinator.async_send_command(
            self._device.device_id,
            {"chs": self._chs_mask, "state": "close"},
        )

