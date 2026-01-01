"""Base entity for YoLink Local integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from yolocal.api import Device
from yolocal.const import DOMAIN
from yolocal.coordinator import YoLocalCoordinator


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
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer="YoLink",
            model=self._device.device_type,
        )

    @property
    def device_state(self) -> dict[str, Any]:
        """Return the current device state."""
        return self.coordinator.get_state(self._device.device_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        state = self.device_state
        return state.get("online", True)

