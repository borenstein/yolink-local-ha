"""Tests for factoring-heavy business logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import asyncio

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


def test_merge_device_state_folds_flat_battery_into_nested_state() -> None:
    """Non-TH MQTT diagnostics should refresh nested state values too."""
    coordinator = make_coordinator()
    device_id = make_device_id("motion-flat")
    coordinator._states[device_id] = {
        "online": True,
        "state": {"battery": 2, "state": "normal"},
    }

    merged = coordinator._merge_device_state(
        device_id,
        {
            "state": "alert",
            "battery": 4,
            "lastReportedAt": "2026-03-09T12:00:00+00:00",
        },
    )

    assert merged["battery"] == 4
    assert merged["state"]["state"] == "alert"
    assert merged["state"]["battery"] == 4


def test_merge_device_state_revives_offline_device_on_fresh_report() -> None:
    """A new report should bring a device back online even without an `online` field."""
    coordinator = make_coordinator()
    device_id = make_device_id("motion")
    coordinator._states[device_id] = {
        "online": False,
        "lastReportedAt": "2026-03-08T12:00:00+00:00",
        "state": {"battery": 1, "state": "normal"},
    }

    merged = coordinator._merge_device_state(
        device_id,
        {
            "lastReportedAt": "2026-03-09T12:00:00+00:00",
            "state": {"battery": 4},
        },
    )

    assert merged["online"] is True
    assert merged["state"] == {"battery": 4, "state": "normal"}


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


def test_merge_thsensor_state_revives_offline_device_on_fresh_report() -> None:
    """TH reports should also restore availability when the hub omits `online`."""
    coordinator = make_coordinator()
    device_id = make_device_id("th-revive")
    coordinator._states[device_id] = {
        "online": False,
        "lastReportedAt": "2026-03-08T12:00:00+00:00",
        "state": {"temperature": 21.5, "humidity": 48},
    }

    merged = coordinator._merge_thsensor_state(
        device_id,
        {
            "lastReportedAt": "2026-03-09T12:00:00+00:00",
            "humidity": 52,
        },
    )

    assert merged["online"] is True
    assert merged["state"]["temperature"] == 21.5
    assert merged["state"]["humidity"] == 52


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


def test_async_update_data_refreshes_battery_from_hub_state() -> None:
    """Scheduled refresh should update diagnostic fields like battery."""
    coordinator = make_coordinator()
    device = make_device(device_id=make_device_id("refresh"), device_type="DoorSensor")
    coordinator._devices[device.device_id] = device
    coordinator._states[device.device_id] = {
        "online": True,
        "state": {"battery": 1, "state": "closed"},
    }

    async def get_state(_device: Device) -> dict[str, object]:
        return {
            "reportAt": "2026-03-09T12:00:00+00:00",
            "state": {"battery": 4},
        }

    coordinator._client = SimpleNamespace(get_state=get_state, host="127.0.0.1")

    refreshed = asyncio.run(coordinator._async_update_data())

    assert refreshed[device.device_id]["lastReportedAt"] == "2026-03-09T12:00:00+00:00"
    assert refreshed[device.device_id]["state"] == {"battery": 4, "state": "closed"}
    assert coordinator._states[device.device_id]["state"]["battery"] == 4


def test_async_update_data_keeps_old_state_when_refresh_fails() -> None:
    """A failed per-device refresh should not drop the cached state."""
    coordinator = make_coordinator()
    device = make_device(device_id=make_device_id("refresh-fail"), device_type="DoorSensor")
    coordinator._devices[device.device_id] = device
    coordinator._states[device.device_id] = {
        "online": True,
        "state": {"battery": 2, "state": "open"},
    }

    async def get_state(_device: Device) -> dict[str, object]:
        raise RuntimeError("boom")

    coordinator._client = SimpleNamespace(get_state=get_state, host="127.0.0.1")

    refreshed = asyncio.run(coordinator._async_update_data())

    assert refreshed[device.device_id] == coordinator._states[device.device_id]
    assert refreshed[device.device_id]["state"]["battery"] == 2


def test_async_update_data_skips_poll_for_recent_report() -> None:
    """Recent MQTT reports should suppress repair polling."""
    coordinator = make_coordinator()
    device = make_device(device_id=make_device_id("recent"), device_type="DoorSensor")
    coordinator._devices[device.device_id] = device
    fresh = datetime.now(UTC) - timedelta(minutes=5)
    coordinator._states[device.device_id] = {
        "online": True,
        "lastReportedAt": fresh.isoformat(),
        "state": {"battery": 3, "state": "closed"},
    }

    calls: list[str] = []

    async def get_state(_device: Device) -> dict[str, object]:
        calls.append("called")
        return {"state": {"battery": 4}}

    coordinator._client = SimpleNamespace(get_state=get_state, host="127.0.0.1")

    refreshed = asyncio.run(coordinator._async_update_data())

    assert calls == []
    assert refreshed[device.device_id]["state"]["battery"] == 3


def test_async_update_data_polls_when_report_is_old() -> None:
    """Old reports should still trigger repair polling."""
    coordinator = make_coordinator()
    device = make_device(device_id=make_device_id("old"), device_type="DoorSensor")
    coordinator._devices[device.device_id] = device
    stale = datetime.now(UTC) - timedelta(minutes=11)
    coordinator._states[device.device_id] = {
        "online": True,
        "lastReportedAt": stale.isoformat(),
        "state": {"battery": 1, "state": "closed"},
    }

    calls: list[str] = []

    async def get_state(_device: Device) -> dict[str, object]:
        calls.append("called")
        return {
            "reportAt": "2026-03-09T12:00:00+00:00",
            "state": {"battery": 4},
        }

    coordinator._client = SimpleNamespace(get_state=get_state, host="127.0.0.1")

    refreshed = asyncio.run(coordinator._async_update_data())

    assert calls == ["called"]
    assert refreshed[device.device_id]["state"]["battery"] == 4


def test_async_setup_publishes_initial_data_to_coordinator() -> None:
    """Initial setup should seed coordinator.data for HA refresh lifecycle."""
    coordinator = make_coordinator()
    device = make_device(device_id=make_device_id("setup"), device_type="DoorSensor")

    async def get_devices() -> list[Device]:
        return [device]

    async def get_state(_device: Device) -> dict[str, object]:
        return {
            "reportAt": "2026-03-09T12:00:00+00:00",
            "state": {"battery": 4, "state": "closed"},
        }

    async def connect_mqtt() -> None:
        return None

    coordinator._client = SimpleNamespace(
        get_devices=get_devices,
        get_state=get_state,
        host="127.0.0.1",
    )
    coordinator._connect_mqtt = connect_mqtt

    asyncio.run(coordinator._async_setup())

    assert coordinator.data is not None
    assert coordinator.data[device.device_id]["state"]["battery"] == 4
    assert (
        coordinator.data[device.device_id]["lastReportedAt"]
        == "2026-03-09T12:00:00+00:00"
    )


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
