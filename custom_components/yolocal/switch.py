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

    entities_by_device_id: dict[str, list[YoLocalSwitch]] = {}

    def build_entities(device) -> list[YoLocalSwitch]:
        if device.device_type != "Outlet":
            return []
        return [YoLocalSwitch(coordinator, device)]

    def add_devices(devices) -> None:
        new_entities: list[YoLocalSwitch] = []
        for device in devices:
            if device.device_id in entities_by_device_id:
                continue
            built = build_entities(device)
            if not built:
                continue
            entities_by_device_id[device.device_id] = built
            new_entities.extend(built)
        if new_entities:
            async_add_entities(new_entities)

    async def remove_devices(device_ids: list[str]) -> None:
        for device_id in device_ids:
            for entity in entities_by_device_id.pop(device_id, []):
                if isinstance(entity, YoLocalEntity):
                    await entity.async_remove_from_hass()

    def handle_registry_change(added_devices, removed_devices) -> None:
        add_devices(added_devices)
        removed_ids = [device.device_id for device in removed_devices]
        if removed_ids:
            hass.async_create_task(remove_devices(removed_ids))

    entry.async_on_unload(
        coordinator.register_device_registry_listener(handle_registry_change)
    )
    add_devices(coordinator.devices.values())


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
