"""Sensor platform for YoLink Local integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
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
    """Set up YoLink sensors from a config entry."""
    coordinator: YoLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for device in coordinator.devices.values():
        if device.device_type == "THSensor":
            entities.append(YoLocalTemperatureSensor(coordinator, device))
            entities.append(YoLocalHumiditySensor(coordinator, device))
            entities.append(YoLocalBatterySensor(coordinator, device))

    async_add_entities(entities)


class YoLocalTemperatureSensor(YoLocalEntity, SensorEntity):
    """Temperature sensor for YoLink THSensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_name = "Temperature"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_temperature"

    @property
    def native_value(self) -> float | None:
        """Return the temperature."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("temperature")
        return self.device_state.get("temperature")

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return additional state attributes."""
        attrs = {}
        
        # Device identification
        attrs["device_id"] = self._device.device_id
        attrs["device_model"] = self._device.device_type
        
        state = self.device_state.get("state", {})
        
        if isinstance(state, dict):
            # Firmware version
            if "version" in state:
                attrs["firmware_version"] = state.get("version")
        
        return attrs


class YoLocalHumiditySensor(YoLocalEntity, SensorEntity):
    """Humidity sensor for YoLink THSensor."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_name = "Humidity"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_humidity"

    @property
    def native_value(self) -> float | None:
        """Return the humidity."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("humidity")
        return self.device_state.get("humidity")

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return additional state attributes."""
        attrs = {}
        
        # Device identification
        attrs["device_id"] = self._device.device_id
        attrs["device_model"] = self._device.device_type
        
        state = self.device_state.get("state", {})
        
        if isinstance(state, dict):
            # Firmware version
            if "version" in state:
                attrs["firmware_version"] = state.get("version")
        
        return attrs


class YoLocalBatterySensor(YoLocalEntity, SensorEntity):
    """Battery sensor for YoLink devices."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_name = "Battery"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_battery"

    @property
    def native_value(self) -> int | None:
        """Return the battery level as percentage."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            level = state.get("battery")
        else:
            level = self.device_state.get("battery")

        if level is None:
            return None
        # YoLink reports 0-4, convert to percentage
        return min(level * 25, 100)

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return additional state attributes."""
        attrs = {}
        
        # Device identification
        attrs["device_id"] = self._device.device_id
        attrs["device_model"] = self._device.device_type
        
        state = self.device_state.get("state", {})
        
        if isinstance(state, dict):
            # Firmware version
            if "version" in state:
                attrs["firmware_version"] = state.get("version")
            # Raw battery level
            if "battery" in state:
                attrs["battery_raw"] = state.get("battery")
        
        return attrs

