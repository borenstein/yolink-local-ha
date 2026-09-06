"""Sensor platform for YoLink Local integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, WATER_METER_UNITS
from .coordinator import YoLocalCoordinator
from .entity import YoLocalEntity


def _state_value(state: dict[str, Any], key: str) -> Any:
    """Read a key from a device state, handling both flat and nested shapes.

    WaterMeterController reports ``state`` as an object
    (``state.valve``, ``state.meter``) while other devices report a flat
    dict at the top level.
    """
    nested = state.get("state")
    if isinstance(nested, dict) and key in nested:
        return nested[key]
    return state.get(key)


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
        elif device.device_type == "WaterMeterController":
            entities.append(YoLocalWaterMeterSensor(coordinator, device))
            entities.append(YoLocalWaterMeterTemperatureSensor(coordinator, device))
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
        return _state_value(self.device_state, "temperature")


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
        level = _state_value(self.device_state, "battery")

        if level is None:
            return None
        # YoLink reports 0-4, convert to percentage
        return min(level * 25, 100)


class YoLocalWaterMeterSensor(YoLocalEntity, SensorEntity):
    """Cumulative water consumption sensor for the YoLink water meter controller."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_name = "Water consumption"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_water_meter"

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the meter's configured volume unit (GAL/CCF/M3/L)."""
        attributes = self.device_state.get("attributes", {})
        meter_unit = attributes.get("meterUnit")
        return WATER_METER_UNITS.get(meter_unit)

    @property
    def native_value(self) -> float | None:
        """Return the cumulative meter reading in the meter's configured unit."""
        meter = _state_value(self.device_state, "meter")
        if meter is None:
            return None
        return float(meter)


class YoLocalWaterMeterTemperatureSensor(YoLocalEntity, SensorEntity):
    """Water temperature sensor for the YoLink water meter controller."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_name = "Water temperature"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_water_temperature"

    @property
    def native_value(self) -> float | None:
        """Return the water temperature."""
        temp = self.device_state.get("temperature")
        if temp is None:
            return None
        return float(temp)

