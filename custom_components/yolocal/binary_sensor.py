"""Binary sensor platform for YoLink Local integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import YoLocalCoordinator
from .entity import YoLocalEntity


DEVICE_TYPE_TO_CLASS = {
    "DoorSensor": BinarySensorDeviceClass.DOOR,
    "LeakSensor": BinarySensorDeviceClass.MOISTURE,
    "MotionSensor": BinarySensorDeviceClass.MOTION,
    "VibrationSensor": BinarySensorDeviceClass.VIBRATION,
}

DEVICE_TYPE_TO_ON_STATE = {
    "DoorSensor": "open",
    "LeakSensor": "alert",
    "MotionSensor": "alert",
    "VibrationSensor": "alert",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up YoLink binary sensors from a config entry."""
    coordinator: YoLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = []
    for device in coordinator.devices.values():
        if device.device_type in DEVICE_TYPE_TO_CLASS:
            entities.append(YoLocalBinarySensor(coordinator, device))

    async_add_entities(entities)


class YoLocalBinarySensor(YoLocalEntity, BinarySensorEntity):
    """Binary sensor for YoLink door/leak/motion sensors."""

    _attr_name = None  # Use device name

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_device_class = DEVICE_TYPE_TO_CLASS.get(device.device_type)
        self._on_state = DEVICE_TYPE_TO_ON_STATE.get(device.device_type, "open")

    @property
    def is_on(self) -> bool | None:
        """Return True if the sensor is triggered."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            sensor_state = state.get("state")
        else:
            sensor_state = state

        if sensor_state is None:
            return None
        return sensor_state == self._on_state

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return additional state attributes."""
        attrs = {}
        
        # Device identification
        attrs["device_id"] = self._device.device_id
        attrs["device_model"] = self._device.device_type
        
        state = self.device_state.get("state", {})
        
        if isinstance(state, dict):
            # Battery level (0-4, convert to percentage)
            if "battery" in state:
                battery_level = state.get("battery")
                if battery_level is not None:
                    attrs["battery_level"] = min(battery_level * 25, 100)
                    attrs["battery_raw"] = battery_level
            
            # Device temperature if available
            if "devTemperature" in state:
                attrs["device_temperature"] = state.get("devTemperature")
            
            # Firmware version
            if "version" in state:
                attrs["firmware_version"] = state.get("version")
        
        return attrs

