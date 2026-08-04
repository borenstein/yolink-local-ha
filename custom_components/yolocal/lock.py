"""Lock platform for YoLink Local integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import YoLocalCoordinator
from .entity import YoLocalEntity

# Supported YoLink lock variants. The newer "LockV2" (e.g. YS7616-UC smart
# deadbolt) nests the lock state under data.state.lock and expects
# params.state.lock on setState; the original "Lock" uses flat data.state /
# params.state.
LOCK_DEVICE_TYPES: set[str] = {"Lock", "LockV2"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up YoLink locks from a config entry."""
    coordinator: YoLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[LockEntity] = []
    for device in coordinator.devices.values():
        if device.device_type in LOCK_DEVICE_TYPES:
            entities.append(YoLocalLock(coordinator, device))

    async_add_entities(entities)


class YoLocalLock(YoLocalEntity, LockEntity):
    """Lock entity for YoLink smart locks (Lock and LockV2)."""

    _attr_name = None  # Use device name

    @property
    def is_locked(self) -> bool | None:
        """Return True if the lock is locked."""
        state = self.device_state.get("state")
        if isinstance(state, dict):
            # LockV2 reports {"state": {"lock": "locked" | "unlocked"}}
            state = state.get("lock")
        if state is None:
            return None
        return state == "locked"

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        await self.coordinator.async_send_command(
            self._device.device_id, self._lock_payload("locked")
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        await self.coordinator.async_send_command(
            self._device.device_id, self._lock_payload("unlocked")
        )

    def _lock_payload(self, lock_state: str) -> dict[str, Any]:
        """Build the setState params for this lock variant."""
        if self._device.device_type == "LockV2":
            return {"state": {"lock": lock_state}}
        return {"state": lock_state}
