"""Sensor platform for YoLink Local integration."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

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
        # All devices get battery, firmware, and last reported sensors
        entities.append(YoLocalBatterySensor(coordinator, device))
        entities.append(YoLocalFirmwareSensor(coordinator, device))
        entities.append(YoLocalLastReportedSensor(coordinator, device))
        # Device-specific sensors
        if device.device_type == "THSensor":
            entities.append(YoLocalTemperatureSensor(coordinator, device))
            entities.append(YoLocalHumiditySensor(coordinator, device))
            entities.append(YoLocalTHModeSensor(coordinator, device))
            entities.append(YoLocalTHIntervalSensor(coordinator, device))
            entities.append(YoLocalTHBatteryTypeSensor(coordinator, device))
            entities.append(YoLocalTHCorrectionSensor(coordinator, device, "temperature"))
            entities.append(YoLocalTHCorrectionSensor(coordinator, device, "humidity"))
            entities.append(YoLocalTHLimitSensor(coordinator, device, "temperature", "max"))
            entities.append(YoLocalTHLimitSensor(coordinator, device, "temperature", "min"))
            entities.append(YoLocalTHLimitSensor(coordinator, device, "humidity", "max"))
            entities.append(YoLocalTHLimitSensor(coordinator, device, "humidity", "min"))
        elif device.device_type == "MotionSensor":
            entities.append(YoLocalDeviceTemperatureSensor(coordinator, device))
            entities.append(YoLocalMotionSensitivitySensor(coordinator, device))
            entities.append(YoLocalMotionNoMotionDelaySensor(coordinator, device))
            entities.append(YoLocalMotionAlertIntervalSensor(coordinator, device))
        elif device.device_type == "LeakSensor":
            entities.append(YoLocalDeviceTemperatureSensor(coordinator, device))
            entities.append(YoLocalLeakSensorModeSensor(coordinator, device))
            entities.append(YoLocalLeakIntervalSensor(coordinator, device))
        elif device.device_type == "DoorSensor":
            entities.append(YoLocalDoorDelaySensor(coordinator, device))
            entities.append(YoLocalDoorOpenRemindDelaySensor(coordinator, device))
            entities.append(YoLocalDoorAlertIntervalSensor(coordinator, device))

    async_add_entities(entities)


# ============================================================================
# Universal Sensors (all devices)
# ============================================================================

class YoLocalBatterySensor(YoLocalEntity, SensorEntity):
    """Battery sensor for YoLink devices."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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


class YoLocalFirmwareSensor(YoLocalEntity, SensorEntity):
    """Firmware version sensor for YoLink devices."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Firmware"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_firmware"

    @property
    def native_value(self) -> str | None:
        """Return the firmware version."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("version")
        return None


class YoLocalLastReportedSensor(YoLocalEntity, SensorEntity):
    """Last reported timestamp sensor for YoLink devices."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Last reported"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_last_reported"

    @property
    def native_value(self) -> datetime | None:
        """Return the last reported timestamp."""
        report_at = self.device_state.get("reportAt")
        if report_at:
            return dt_util.parse_datetime(report_at)
        return None


# ============================================================================
# THSensor-specific sensors
# ============================================================================

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
        return None


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
        return None


class YoLocalTHModeSensor(YoLocalEntity, SensorEntity):
    """Temperature unit mode sensor for YoLink THSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Temperature unit"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_temp_unit"

    @property
    def native_value(self) -> str | None:
        """Return the temperature unit mode."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            mode = state.get("mode")
            return "Fahrenheit" if mode == "f" else "Celsius" if mode == "c" else mode
        return None


class YoLocalTHIntervalSensor(YoLocalEntity, SensorEntity):
    """Reporting interval sensor for YoLink THSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "min"
    _attr_name = "Reporting interval"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_interval"

    @property
    def native_value(self) -> int | None:
        """Return the reporting interval."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("interval")
        return None


class YoLocalTHBatteryTypeSensor(YoLocalEntity, SensorEntity):
    """Battery type sensor for YoLink THSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Battery type"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_battery_type"

    @property
    def native_value(self) -> str | None:
        """Return the battery type."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("batteryType")
        return None


class YoLocalTHCorrectionSensor(YoLocalEntity, SensorEntity):
    """Calibration correction sensor for YoLink THSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: YoLocalCoordinator, device, measurement_type: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._measurement_type = measurement_type
        if measurement_type == "temperature":
            self._attr_name = "Temperature correction"
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_unique_id = f"{device.device_id}_temp_correction"
        else:
            self._attr_name = "Humidity correction"
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_unique_id = f"{device.device_id}_humidity_correction"

    @property
    def native_value(self) -> int | None:
        """Return the calibration correction value."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            if self._measurement_type == "temperature":
                return state.get("tempCorrection")
            else:
                return state.get("humidityCorrection")
        return None


class YoLocalTHLimitSensor(YoLocalEntity, SensorEntity):
    """Alarm threshold limit sensor for YoLink THSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: YoLocalCoordinator, device, measurement_type: str, limit_type: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._measurement_type = measurement_type
        self._limit_type = limit_type
        limit_name = "max" if limit_type == "max" else "min"
        if measurement_type == "temperature":
            self._attr_name = f"Temperature {limit_name} threshold"
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_unique_id = f"{device.device_id}_temp_{limit_type}"
        else:
            self._attr_name = f"Humidity {limit_name} threshold"
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_unique_id = f"{device.device_id}_humidity_{limit_type}"

    @property
    def native_value(self) -> int | float | None:
        """Return the alarm threshold."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            if self._measurement_type == "temperature":
                limits = state.get("tempLimit", {})
            else:
                limits = state.get("humidityLimit", {})
            if isinstance(limits, dict):
                return limits.get(self._limit_type)
        return None


# ============================================================================
# MotionSensor/LeakSensor device temperature sensor
# ============================================================================

class YoLocalDeviceTemperatureSensor(YoLocalEntity, SensorEntity):
    """Device internal temperature sensor for YoLink sensors."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Device temperature"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_dev_temperature"

    @property
    def native_value(self) -> int | None:
        """Return the device temperature."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("devTemperature")
        return None


# ============================================================================
# MotionSensor-specific sensors
# ============================================================================

class YoLocalMotionSensitivitySensor(YoLocalEntity, SensorEntity):
    """Sensitivity sensor for YoLink MotionSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Sensitivity"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_sensitivity"

    @property
    def native_value(self) -> int | None:
        """Return the sensitivity level (1-5)."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("sensitivity")
        return None


class YoLocalMotionNoMotionDelaySensor(YoLocalEntity, SensorEntity):
    """No-motion delay sensor for YoLink MotionSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "min"
    _attr_name = "No-motion delay"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_nomotion_delay"

    @property
    def native_value(self) -> int | None:
        """Return the no-motion delay in minutes."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("nomotionDelay")
        return None


class YoLocalMotionAlertIntervalSensor(YoLocalEntity, SensorEntity):
    """Alert interval sensor for YoLink MotionSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "min"
    _attr_name = "Alert interval"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_alert_interval"

    @property
    def native_value(self) -> int | None:
        """Return the alert interval."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("alertInterval")
        return None


# ============================================================================
# LeakSensor-specific sensors
# ============================================================================

class YoLocalLeakSensorModeSensor(YoLocalEntity, SensorEntity):
    """Sensor mode sensor for YoLink LeakSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Sensor mode"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_sensor_mode"

    @property
    def native_value(self) -> str | None:
        """Return the sensor mode."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("sensorMode")
        return None


class YoLocalLeakIntervalSensor(YoLocalEntity, SensorEntity):
    """Reporting interval sensor for YoLink LeakSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "min"
    _attr_name = "Reporting interval"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_interval"

    @property
    def native_value(self) -> int | None:
        """Return the reporting interval."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("interval")
        return None


# ============================================================================
# DoorSensor-specific sensors
# ============================================================================

class YoLocalDoorDelaySensor(YoLocalEntity, SensorEntity):
    """Delay sensor for YoLink DoorSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "s"
    _attr_name = "Delay"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_delay"

    @property
    def native_value(self) -> int | None:
        """Return the delay in seconds."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("delay")
        return None


class YoLocalDoorOpenRemindDelaySensor(YoLocalEntity, SensorEntity):
    """Open remind delay sensor for YoLink DoorSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "min"
    _attr_name = "Open remind delay"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_open_remind_delay"

    @property
    def native_value(self) -> int | None:
        """Return the open remind delay in minutes."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("openRemindDelay")
        return None


class YoLocalDoorAlertIntervalSensor(YoLocalEntity, SensorEntity):
    """Alert interval sensor for YoLink DoorSensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "min"
    _attr_name = "Alert interval"

    def __init__(self, coordinator: YoLocalCoordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.device_id}_alert_interval"

    @property
    def native_value(self) -> int | None:
        """Return the alert interval."""
        state = self.device_state.get("state", {})
        if isinstance(state, dict):
            return state.get("alertInterval")
        return None
