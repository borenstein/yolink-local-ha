"""Base entity for YoLink Local integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Device
from .const import DOMAIN
from .coordinator import YoLocalCoordinator


class YoLocalEntity(CoordinatorEntity[YoLocalCoordinator]):
    """Base entity for YoLink Local devices."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: YoLocalCoordinator,
        device: Device,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = device.device_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this entity."""
        # Show both model and device type if model is available
        if self._device.model:
            model = f"{self._device.model} ({self._device.display_type})"
        else:
            model = self._device.display_type

        return DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer="YoLink",
            model=model,
            serial_number=self._device.device_id,
        )

    @property
    def device_state(self) -> dict[str, Any]:
        """Return the current device state."""
        return self.coordinator.get_state(self._device.device_id)

    @property
    def nested_device_state(self) -> dict[str, Any]:
        """Return the nested `state` object when available."""
        state = self.device_state.get("state")
        if isinstance(state, dict):
            return state
        return {}

    def state_value(self, key: str, fallback: bool = False) -> Any:
        """Return a nested state value, optionally falling back to top-level state."""
        value = self.nested_device_state.get(key)
        if value is not None or not fallback:
            return value
        return self.device_state.get(key)

    async def async_remove_from_hass(self) -> None:
        """Remove this entity from HA, including its registry entry when present."""
        entity_id = getattr(self, "entity_id", None)
        if entity_id:
            registry = er.async_get(self.coordinator.hass)
            if registry.async_get(entity_id) is not None:
                registry.async_remove(entity_id)
                return
        if hasattr(self, "async_remove"):
            await self.async_remove()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # First check if coordinator is available
        if not super().available:
            return False

        state = self.device_state
        # Check if device is marked online
        if not state.get("online", True):
            return False
        # Check if device has reported within last 12 hours
        report_at = state.get("lastReportedAt")
        if report_at:
            try:
                last_report = dt_util.parse_datetime(report_at)
                if last_report:
                    now = dt_util.utcnow()
                    time_since_report = now - last_report
                    if time_since_report > timedelta(hours=12):
                        return False
            except Exception:
                pass
        return True
