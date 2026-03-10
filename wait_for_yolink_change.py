#!/usr/bin/env python3
"""Standalone YoLink sensor watcher (no Home Assistant dependency)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import Any

import aiohttp
import paho.mqtt.client as mqtt

from yolink_tooling_common import (
    HUB_HTTP_PORT,
    HUB_MQTT_PORT,
    merge_state,
    normalize_event_payload,
    normalize_host,
)


def extract_th(state: dict[str, Any]) -> dict[str, float | int | None]:
    """Extract TH values from device state payload."""
    nested = state.get("state")
    if isinstance(nested, dict):
        return {
            "temperature": nested.get("temperature"),
            "humidity": nested.get("humidity"),
        }
    return {"temperature": None, "humidity": None}


def extract_th_unit(state: dict[str, Any]) -> str | None:
    """Extract TH unit from payload with tolerant key/value handling."""
    nested = state.get("state")
    if not isinstance(nested, dict):
        return None
    mode = (
        nested.get("mode")
        or nested.get("tempUnit")
        or nested.get("temperatureUnit")
        or nested.get("unit")
    )
    if mode is None:
        return None
    normalized = str(mode).strip().lower()
    if normalized in {"c", "0", "celsius", "centigrade", "cel"}:
        return "Celsius"
    if normalized in {"f", "1", "fahrenheit", "fahr"}:
        return "Fahrenheit"
    return str(mode)


def format_temp_celsius(value: Any) -> str:
    """Format temperature as Celsius (payload numeric scale)."""
    if value is None:
        return "None"
    return f"{value} C"


def format_humidity(value: Any) -> str:
    """Format humidity value with percentage."""
    if value is None:
        return "None"
    return f"{value}%"


def extract_motion(state: dict[str, Any]) -> str | None:
    """Extract motion state from current payload."""
    nested = state.get("state")
    if isinstance(nested, dict):
        value = nested.get("state")
        if isinstance(value, str):
            return value
        return None
    if isinstance(nested, str):
        return nested
    return None


async def get_token(
    session: aiohttp.ClientSession,
    host: str,
    client_id: str,
    client_secret: str,
) -> str:
    """Get OAuth token from hub."""
    url = f"http://{host}:{HUB_HTTP_PORT}/open/yolink/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    async with session.post(url, data=data) as resp:
        resp.raise_for_status()
        result = await resp.json()
    token = result.get("access_token")
    if not token:
        raise RuntimeError(f"Auth failed: {result}")
    return token


async def api_request(
    session: aiohttp.ClientSession,
    host: str,
    token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Call local hub API."""
    url = f"http://{host}:{HUB_HTTP_PORT}/open/yolink/v2/api"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    async with session.post(url, json=payload, headers=headers) as resp:
        resp.raise_for_status()
        result = await resp.json()
    if result.get("code") != "000000":
        raise RuntimeError(f"API error: {result}")
    return result.get("data", {})


def get_device_defaults(kind: str) -> tuple[str, str]:
    """Return default device id and name for a sensor kind."""
    if kind == "th":
        return (
            os.getenv("YOLINK_TH_8003_SERIAL") or "",
            os.getenv("YOLINK_TH_DEVICE_NAME", ""),
        )
    if kind == "temp":
        return (
            os.getenv("YOLINK_TEMP_8004_SERIAL") or "",
            os.getenv("YOLINK_TEMP_DEVICE_NAME", ""),
        )
    if kind == "motion":
        return (
            os.getenv("YOLINK_MOTION_7805_SERIAL")
            or os.getenv("YOLINK_MOTION_7804_SERIAL")
            or "",
            os.getenv("YOLINK_MOTION_DEVICE_NAME", "entrance"),
        )
    if kind == "door":
        return (
            os.getenv("YOLINK_DOOR_7704_SERIAL") or "",
            os.getenv("YOLINK_DOOR_DEVICE_NAME", ""),
        )
    if kind == "tilt":
        return (
            os.getenv("YOLINK_TILT_7706_SERIAL") or "",
            os.getenv("YOLINK_TILT_DEVICE_NAME", ""),
        )
    if kind == "leak":
        return (
            os.getenv("YOLINK_LEAK_7903_SERIAL") or "",
            os.getenv("YOLINK_LEAK_DEVICE_NAME", ""),
        )
    if kind == "lock":
        return (os.getenv("YOLINK_LOCK_MODEL_NUMBER_SERIAL") or "", "")
    return "", ""


async def run(args: argparse.Namespace) -> int:
    """Run watcher until the selected value changes or timeout occurs."""
    host = normalize_host(args.host)
    kind = args.kind
    expected_type_map = {
        "th": "THSensor",
        "temp": "THSensor",
        "motion": "MotionSensor",
        "door": "DoorSensor",
        "tilt": "DoorSensor",
        "leak": "LeakSensor",
        "lock": "Lock",
    }
    expected_type = expected_type_map[kind]
    get_state_method = f"{expected_type}.getState"

    session = aiohttp.ClientSession()
    mqtt_client: mqtt.Client | None = None
    done = asyncio.Event()

    try:
        token = await get_token(
            session=session,
            host=host,
            client_id=args.client_id,
            client_secret=args.client_secret,
        )
        devices_data = await api_request(
            session=session,
            host=host,
            token=token,
            payload={"method": "Home.getDeviceList"},
        )

        devices = devices_data.get("devices", [])
        device = None
        if args.device_id:
            device = next((d for d in devices if d.get("deviceId") == args.device_id), None)
        elif args.device_name:
            name_lc = args.device_name.lower()
            device = next(
                (d for d in devices if name_lc in (d.get("name", "").lower())),
                None,
            )

        if device is None:
            print(f"ERROR: {expected_type} not found (check --device-id/--device-name)")
            return 2
        if device.get("type") != expected_type:
            print(
                f"ERROR: Device {device.get('deviceId')} is {device.get('type')}, expected {expected_type}"
            )
            return 2

        device_id = device.get("deviceId")
        state = await api_request(
            session=session,
            host=host,
            token=token,
            payload={
                "method": get_state_method,
                "targetDevice": device_id,
                "token": device.get("token"),
            },
        )
        current_state = state
        loop = asyncio.get_running_loop()

        if kind in {"th", "temp"}:
            baseline_th = extract_th(current_state)
            baseline_unit = extract_th_unit(current_state)
            print(f"Watching device: {device.get('name')} ({device_id})")
            print(
                "Initial temperature="
                f"{format_temp_celsius(baseline_th['temperature'])}, "
                f"humidity={format_humidity(baseline_th['humidity'])}"
            )
            print(f"Initial unit={baseline_unit}")
            th_field = "temperature" if kind == "temp" else args.field
            print(f"Waiting up to {args.timeout}s for {th_field} change...")
        elif kind == "motion":
            baseline_motion = extract_motion(current_state)
            print(f"Watching device: {device.get('name')} ({device_id})")
            print(f"Initial motion state={baseline_motion}")
            print(f"Waiting up to {args.timeout}s for motion state change...")
        else:
            baseline_state = extract_motion(current_state)
            print(f"Watching device: {device.get('name')} ({device_id})")
            print(f"Initial state={baseline_state}")
            print(f"Waiting up to {args.timeout}s for state change...")

        def on_message(
            client: mqtt.Client,
            userdata: Any,
            msg: mqtt.MQTTMessage,
        ) -> None:
            nonlocal current_state
            del client, userdata

            try:
                payload = json.loads(msg.payload.decode())
                event_device_id, event_data = normalize_event_payload(payload)
            except Exception:
                return

            if event_device_id != device_id:
                return

            current_state = merge_state(current_state, event_data)

            if kind in {"th", "temp"}:
                now = extract_th(current_state)
                now_unit = extract_th_unit(current_state)
                temp_changed = now["temperature"] != baseline_th["temperature"]
                humidity_changed = now["humidity"] != baseline_th["humidity"]
                unit_changed = now_unit != baseline_unit
                th_field = "temperature" if kind == "temp" else args.field
                matched = (
                    (th_field == "temperature" and temp_changed)
                    or (th_field == "humidity" and humidity_changed)
                    or (th_field == "unit" and unit_changed)
                    or (th_field == "both" and (temp_changed or humidity_changed))
                )
                if matched:
                    print("CHANGE DETECTED")
                    print(
                        "temperature: "
                        f"{format_temp_celsius(baseline_th['temperature'])} "
                        f"-> {format_temp_celsius(now['temperature'])}"
                    )
                    print(
                        "humidity: "
                        f"{format_humidity(baseline_th['humidity'])} "
                        f"-> {format_humidity(now['humidity'])}"
                    )
                    print(f"unit: {baseline_unit} -> {now_unit}")
                    loop.call_soon_threadsafe(done.set)
            elif kind == "motion":
                now_motion = extract_motion(current_state)
                if now_motion != baseline_motion:
                    print("CHANGE DETECTED")
                    print(f"motion_state: {baseline_motion} -> {now_motion}")
                    loop.call_soon_threadsafe(done.set)
            else:
                now_state = extract_motion(current_state)
                if now_state != baseline_state:
                    print("CHANGE DETECTED")
                    print(f"state: {baseline_state} -> {now_state}")
                    loop.call_soon_threadsafe(done.set)

        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqtt_client.username_pw_set(args.client_id, token)
        mqtt_client.on_message = on_message
        mqtt_client.connect_async(host, HUB_MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
        await asyncio.sleep(1)
        mqtt_client.subscribe(f"ylsubnet/{args.net_id}/+/report")

        try:
            await asyncio.wait_for(done.wait(), timeout=args.timeout)
            return 0
        except asyncio.TimeoutError:
            print("TIMEOUT: no matching change observed")
            return 1
    finally:
        if mqtt_client:
            mqtt_client.disconnect()
            time.sleep(0.2)
            mqtt_client.loop_stop()
        await session.close()


def parse_args() -> argparse.Namespace:
    """Parse command line args with env var fallbacks."""
    parser = argparse.ArgumentParser(
        description="Wait for YoLink TH or motion MQTT state change",
    )
    parser.add_argument(
        "--kind",
        choices=("th", "temp", "motion", "door", "tilt", "leak", "lock"),
        default=os.getenv("YOLINK_KIND", "th"),
    )
    parser.add_argument(
        "--host",
        default=os.getenv("YOLINK_HOST"),
        required=os.getenv("YOLINK_HOST") is None,
    )
    parser.add_argument(
        "--client-id",
        default=os.getenv("YOLINK_CLIENT_ID"),
        required=os.getenv("YOLINK_CLIENT_ID") is None,
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("YOLINK_CLIENT_SECRET"),
        required=os.getenv("YOLINK_CLIENT_SECRET") is None,
    )
    parser.add_argument(
        "--net-id",
        default=os.getenv("YOLINK_NET_ID") or os.getenv("YOLINK_NET"),
        required=os.getenv("YOLINK_NET_ID") is None and os.getenv("YOLINK_NET") is None,
    )
    parser.add_argument("--device-id", default=None)
    parser.add_argument("--device-name", default=None)
    parser.add_argument("--timeout", type=int, default=int(os.getenv("YOLINK_TIMEOUT", "900")))
    parser.add_argument(
        "--field",
        choices=("temperature", "humidity", "unit", "both"),
        default=os.getenv("YOLINK_FIELD", "both"),
        help="TH-only: which value change to watch",
    )

    args = parser.parse_args()
    default_id, default_name = get_device_defaults(args.kind)
    if not args.device_id:
        args.device_id = default_id or None
    if not args.device_name:
        args.device_name = default_name or None
    if not args.device_id and not args.device_name:
        parser.error(
            "Provide --device-id/--device-name or set kind-specific env vars "
            "(YOLINK_*_SERIAL)."
        )
    return args


def main() -> int:
    """CLI entrypoint."""
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
