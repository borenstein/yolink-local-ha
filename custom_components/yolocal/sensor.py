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

from yolocal.const import DOMAIN
from yolocal.coordinator import YoLocalCoordinator
from yolocal.entity import YoLocalEntity


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

