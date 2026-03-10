"""Tests for factoring-heavy business logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from custom_components.yolocal.api.device import Device
from custom_components.yolocal.coordinator import YoLocalCoordinator
from custom_components.yolocal.entity import YoLocalEntity
from custom_components.yolocal.sensor import YoLocalTHLimitSensor


def make_device_id(label: str = "device") -> str:
    """Create a generic test device id."""
    return f"test-{label}"


def make_app_eui(model_num: str) -> str:
    """Create a synthetic appEui with the requested model number."""
    return f"000000{model_num}000000"


def make_device(
    *,
    device_id: str = make_device_id(),
    device_type: str = "THSensor",
    display_type: str | None = None,
    model: str | None = "YS8001-UC",
) -> Device:
    """Create a test device."""
    return Device(
        device_id=device_id,
        name="Test Device",
        token="token",
        device_type=device_type,
        display_type=display_type or device_type,
        model=model,
    )


def make_coordinator() -> YoLocalCoordinator:
    """Create a coordinator with stub dependencies."""
    hass = SimpleNamespace(async_create_task=lambda coro: SimpleNamespace(coro=coro))
    token_manager = SimpleNamespace(client_id="client")
    client = SimpleNamespace(host="127.0.0.1")
    session = SimpleNamespace()
    return YoLocalCoordinator(
        hass=hass,
        client=client,
        token_manager=token_manager,
        session=session,
        net_id="net",
    )


def test_merge_nested_state_covers_all_shapes() -> None:
    """Nested state merge should preserve prior detail across payload shapes."""
    coordinator = make_coordinator()

    assert coordinator._merge_nested_state({"battery": 4}, {"state": "alert"}) == {
        "battery": 4,
        "state": "alert",
    }
    assert coordinator._merge_nested_state("open", {"state": "closed"}) == {
        "state": "closed"
    }
    assert coordinator._merge_nested_state({"battery": 4}, {"humidity": 61}) == {
        "battery": 4,
        "humidity": 61,
    }
    assert coordinator._merge_nested_state({"battery": 4}, None) is None


def test_merge_device_state_preserves_existing_nested_fields() -> None:
    """Non-TH devices should deep-merge nested `state` payloads."""
    coordinator = make_coordinator()
    device_id = make_device_id("door")
    coordinator._states[device_id] = {
        "online": True,
        "state": {"battery": 4, "state": "open"},
    }

    merged = coordinator._merge_device_state(
        device_id,
        {"state": {"state": "closed"}, "lastReportedAt": "2026-03-09T12:00:00+00:00"},
    )

    assert merged["online"] is True
    assert merged["lastReportedAt"] == "2026-03-09T12:00:00+00:00"
    assert merged["state"] == {"battery": 4, "state": "closed"}


def test_merge_thsensor_state_preserves_diagnostics_and_ignores_empty_updates() -> None:
    """TH events should retain cached diagnostics and skip empty sentinel updates."""
    coordinator = make_coordinator()
    device_id = make_device_id("th")
    coordinator._states[device_id] = {
        "version": "old-top-level",
        "state": {
            "battery": 4,
            "version": "1.0.0",
            "temperature": 21.5,
            "humidity": 48,
        },
    }

    merged = coordinator._merge_thsensor_state(
        device_id,
        {
            "temperature": None,
            "humidity": 52,
            "mode": None,
            "lastReportedAt": "2026-03-09T12:00:00+00:00",
            "state": {"battery": 3},
        },
    )

    assert merged["lastReportedAt"] == "2026-03-09T12:00:00+00:00"
    assert merged["state"]["battery"] == 3
    assert merged["state"]["humidity"] == 52
    assert merged["state"]["temperature"] == 21.5
    assert merged["state"]["version"] == "1.0.0"
    assert "lastReportedAt" not in merged["state"]


def test_merge_device_state_strips_inaccurate_battery_type() -> None:
    """Battery type should not be retained in cached state."""
    coordinator = make_coordinator()
    device_id = make_device_id("motion")
    coordinator._states[device_id] = {
        "state": {
            "battery": 4,
            "batteryType": "Li",
            "state": "normal",
        }
    }

    merged = coordinator._merge_device_state(
        device_id,
        {
            "online": True,
            "state": {
                "battery": 4,
                "batteryType": "Li",
                "state": "alert",
            },
        },
    )

    assert "batteryType" not in merged
    assert "batteryType" not in merged["state"]
    assert merged["state"]["state"] == "alert"


def test_state_value_prefers_nested_with_top_level_fallback() -> None:
    """Entity helper should prefer nested state and only fall back when requested."""
    coordinator = make_coordinator()
    device = make_device()
    coordinator._states[device.device_id] = {
        "version": "top",
        "state": {"version": "nested"},
    }
    entity = YoLocalEntity(coordinator, device)

    assert entity.state_value("version") == "nested"
    assert entity.state_value("missing") is None
    assert entity.state_value("version", fallback=True) == "nested"
    assert entity.state_value("other", fallback=True) is None

    coordinator._states[device.device_id] = {"version": "top"}
    assert entity.state_value("version", fallback=True) == "top"


def test_entity_availability_handles_offline_and_stale_devices() -> None:
    """Availability logic should be conservative for offline or stale devices."""
    coordinator = make_coordinator()
    device = make_device(device_type="DoorSensor", display_type="DoorSensor")
    entity = YoLocalEntity(coordinator, device)

    coordinator._states[device.device_id] = {"online": False}
    assert entity.available is False

    stale = datetime.now(UTC) - timedelta(hours=13)
    coordinator._states[device.device_id] = {
        "online": True,
        "lastReportedAt": stale.isoformat(),
    }
    assert entity.available is False

    fresh = datetime.now(UTC) - timedelta(hours=1)
    coordinator._states[device.device_id] = {
        "online": True,
        "lastReportedAt": fresh.isoformat(),
    }
    assert entity.available is True


def test_th_limit_sensor_filters_sentinel_values() -> None:
    """Threshold sensor should reject unrealistic sentinel values."""
    coordinator = make_coordinator()
    device = make_device()
    coordinator._states[device.device_id] = {"state": {"tempLimit": {"max": 999}}}
    sensor = YoLocalTHLimitSensor(coordinator, device, "temperature", "max")
    assert sensor.native_value is None

    coordinator._states[device.device_id] = {"state": {"humidityLimit": {"min": -1}}}
    sensor = YoLocalTHLimitSensor(coordinator, device, "humidity", "min")
    assert sensor.native_value is None

    coordinator._states[device.device_id] = {"state": {"tempLimit": {"max": 32}}}
    sensor = YoLocalTHLimitSensor(coordinator, device, "temperature", "max")
    assert sensor.native_value == 32


def test_device_from_api_preserves_motion_sensor_type_for_7805() -> None:
    """YS7805-UC should remain a MotionSensor with the derived model number."""
    device = Device.from_api(
        {
            "deviceId": make_device_id("motion-api"),
            "name": "Terrace motion sensor",
            "token": "token",
            "type": "MotionSensor",
            "appEui": make_app_eui("7805"),
        }
    )

    assert device.device_type == "MotionSensor"
    assert device.display_type == "MotionSensor"
    assert device.model == "YS7805-UC"


def test_device_from_api_preserves_door_sensor_type_for_7707() -> None:
    """YS7707-UC should follow generic door-sensor handling when the hub reports it."""
    device = Device.from_api(
        {
            "deviceId": make_device_id("door-api"),
            "name": "Side door contact",
            "token": "token",
            "type": "DoorSensor",
            "appEui": make_app_eui("7707"),
        }
    )

    assert device.device_type == "DoorSensor"
    assert device.display_type == "DoorSensor"
    assert device.model == "YS7707-UC"
