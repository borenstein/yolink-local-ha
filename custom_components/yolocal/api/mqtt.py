"""MQTT client for YoLink Local Hub real-time events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceEvent:
    """Represents an event received from a device."""

    device_id: str
    event: str
    data: dict[str, Any]
    raw: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> DeviceEvent:
        """Create a DeviceEvent from MQTT payload."""
        return cls(
            device_id=payload.get("deviceId", ""),
            event=payload.get("event", ""),
            data=payload.get("data", {}),
            raw=payload,
        )


EventCallback = Callable[[DeviceEvent], None]


class YoLinkMQTTClient:
    """MQTT client for receiving real-time device events."""

    def __init__(
        self,
        host: str,
        net_id: str,
        client_id: str,
        access_token: str,
        port: int = 18080,
    ) -> None:
        """Initialize the MQTT client."""
        self._host = host
        self._port = port
        self._net_id = net_id
        self._client_id = client_id
        self._access_token = access_token
        self._client: mqtt.Client | None = None
        self._callbacks: list[EventCallback] = []
        self._connected = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def topic(self) -> str:
        """Return the subscription topic."""
        return f"ylsubnet/{self._net_id}/+/report"

    def subscribe(self, callback: EventCallback) -> Callable[[], None]:
        """Subscribe to device events. Returns unsubscribe function."""
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback)

    async def connect(self) -> None:
        """Connect to the MQTT broker."""
        self._loop = asyncio.get_running_loop()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.username_pw_set(self._client_id, self._access_token)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()

        # Wait for connection with timeout
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            raise ConnectionError("Timed out connecting to MQTT broker")

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._connected.clear()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: Any,
        properties: Any = None,
    ) -> None:
        """Handle connection established."""
        if rc == 0 or str(rc) == "Success":
            _LOGGER.info("Connected to YoLink MQTT broker")
            client.subscribe(self.topic)
            if self._loop:
                self._loop.call_soon_threadsafe(self._connected.set)
        else:
            _LOGGER.error("MQTT connection failed: %s", rc)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any,
        rc: Any,
        properties: Any = None,
    ) -> None:
        """Handle disconnection."""
        _LOGGER.warning("Disconnected from MQTT broker: %s", rc)
        self._connected.clear()

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        msg: mqtt.MQTTMessage,
    ) -> None:
        """Handle incoming message."""
        try:
            payload = json.loads(msg.payload.decode())
            event = DeviceEvent.from_payload(payload)
            for callback in self._callbacks:
                try:
                    callback(event)
                except Exception:
                    _LOGGER.exception("Error in event callback")
        except json.JSONDecodeError:
            _LOGGER.error("Failed to decode MQTT message: %s", msg.payload)
        except Exception:
            _LOGGER.exception("Error processing MQTT message")

