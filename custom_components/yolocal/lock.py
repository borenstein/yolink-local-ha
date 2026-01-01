"""Lock platform for YoLink Local integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
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
    """Set up YoLink locks from a config entry."""
    coordinator: YoLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[LockEntity] = []
    for device in coordinator.devices.values():
        if device.device_type == "Lock":
            entities.append(YoLocalLock(coordinator, device))

    async_add_entities(entities)


class YoLocalLock(YoLocalEntity, LockEntity):
    """Lock entity for YoLink smart lock."""

    _attr_name = None  # Use device name

    @property
    def is_locked(self) -> bool | None:
        """Return True if the lock is locked."""
        state = self.device_state.get("state")
        if state is None:
            return None
        return state == "locked"

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        await self.coordinator.async_send_command(
            self._device.device_id,
            {"state": "locked"},
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        await self.coordinator.async_send_command(
            self._device.device_id,
            {"state": "unlocked"},
        )

