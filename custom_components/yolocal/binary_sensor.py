"""Binary sensor platform for YoLink Local integration."""

from __future__ import annotations

from typing import Any

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
}

DEVICE_TYPE_TO_ON_STATE = {
    "DoorSensor": "open",
    "LeakSensor": "alert",
}


def _state_dict(state: dict[str, Any]) -> dict[str, Any]:
    """Return the nested state object for devices that expose one.

    WaterMeterController reports ``state`` as an object (``state.valve``,
    ``state.waterFlowing``) while other devices report a flat dict.
    """
    nested = state.get("state")
    if isinstance(nested, dict):
        return nested
    return state


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
        elif device.device_type == "WaterMeterController":
            entities.append(YoLocalWaterFlowBinarySensor(coordinator, device))
            entities.append(YoLocalWaterLeakBinarySensor(coordinator, device))

    async_add_entities(entities)


class YoLocalBinarySensor(YoLocalEntity, BinarySensorEntity):
    """Binary sensor for YoLink door/leak sensors."""

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


class YoLocalWaterFlowBinarySensor(YoLocalEntity, BinarySensorEntity):
    """Water-flowing binary sensor for the YoLink water meter controller."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_name = "Water flowing"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_water_flow"

    @property
    def is_on(self) -> bool | None:
        """Return True while water is flowing."""
        water_flow = _state_dict(self.device_state).get("waterFlowing")
        if water_flow is None:
            return None
        return bool(water_flow)


class YoLocalWaterLeakBinarySensor(YoLocalEntity, BinarySensorEntity):
    """Leak-detected binary sensor for the YoLink water meter controller."""

    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_name = "Leak"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_leak"

    @property
    def is_on(self) -> bool | None:
        """Return True when a leak is detected."""
        alarm = self.device_state.get("alarm", {})
        if not isinstance(alarm, dict):
            return None
        leak = alarm.get("leak")
        if leak is None:
            return None
        return bool(leak)
