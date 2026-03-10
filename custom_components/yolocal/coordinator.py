"""Data coordinator for YoLink Local integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import (
    Device,
    DeviceEvent,
    TokenManager,
    YoLinkClient,
    YoLinkMQTTClient,
)
from .const import STATE_REFRESH_INTERVAL

_LOGGER = logging.getLogger(__name__)


class YoLocalCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator for YoLink Local devices.

    Manages MQTT subscription for real-time updates and provides
    device state to entities.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: YoLinkClient,
        token_manager: TokenManager,
        session: aiohttp.ClientSession,
        net_id: str,
        mqtt_port: int = 18080,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="YoLink Local",
            update_interval=STATE_REFRESH_INTERVAL,
        )
        self._client = client
        self._token_manager = token_manager
        self._session = session
        self._net_id = net_id
        self._mqtt_port = mqtt_port
        self._mqtt_client: YoLinkMQTTClient | None = None
        self._devices: dict[str, Device] = {}
        self._states: dict[str, dict[str, Any]] = {}
        self._reconnect_task: asyncio.Task[None] | None = None
        self._shutdown = False

    @property
    def devices(self) -> dict[str, Device]:
        """Return the device registry."""
        return self._devices

    async def _async_setup(self) -> None:
        """Set up the coordinator: fetch devices and connect MQTT."""
        devices = await self._client.get_devices()
        self._devices = {d.device_id: d for d in devices}

        for device in devices:
            try:
                state = await self._client.get_state(device)
                state = self._sanitize_state_payload(state)
                # HTTP `getState` uses `reportAt`; store a normalized internal field
                # that later MQTT `time` updates can overwrite consistently.
                if state.get("reportAt") and "lastReportedAt" not in state:
                    state["lastReportedAt"] = state["reportAt"]
                self._states[device.device_id] = state
            except Exception:
                _LOGGER.warning("Failed to get initial state for %s", device.name)
                self._states[device.device_id] = {}

        try:
            await self._connect_mqtt()
        except Exception:
            _LOGGER.warning(
                "Initial MQTT connection failed; reconnecting in background",
                exc_info=True,
            )
            self._on_mqtt_disconnect()

    async def async_shutdown(self) -> None:
        """Shut down the coordinator."""
        self._shutdown = True
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self._mqtt_client:
            await self._mqtt_client.disconnect()
            self._mqtt_client = None
        await self._session.close()

    async def _connect_mqtt(self) -> None:
        """Connect to MQTT broker."""
        token = await self._token_manager.get_token()
        host = self._client.host

        mqtt_client = YoLinkMQTTClient(
            host=host,
            net_id=self._net_id,
            client_id=self._token_manager.client_id,
            access_token=token,
            port=self._mqtt_port,
        )
        mqtt_client.subscribe(self._on_device_event)
        mqtt_client.on_disconnect(self._on_mqtt_disconnect)

        try:
            await mqtt_client.connect()
            self._mqtt_client = mqtt_client
            _LOGGER.info("Connected to YoLink MQTT broker")
        except Exception:
            try:
                await mqtt_client.disconnect()
            except Exception:
                _LOGGER.debug(
                    "Error while cleaning up failed MQTT client",
                    exc_info=True,
                )
            _LOGGER.exception("Failed to connect to MQTT broker")
            raise

    @callback
    def _on_device_event(self, event: DeviceEvent) -> None:
        """Handle a device event from MQTT."""
        device_id = event.device_id
        device = self._devices.get(device_id)
        if device is None:
            _LOGGER.debug("Ignoring event for unknown device: %s", device_id)
            return

        event_data = event.data if isinstance(event.data, dict) else {}
        if device.device_type == "THSensor":
            self._update_device_state(
                device_id,
                self._merge_thsensor_state(device_id, event_data),
            )
            return

        self._update_device_state(
            device_id,
            self._merge_device_state(device_id, event_data),
        )

    def _update_device_state(self, device_id: str, state: dict[str, Any]) -> None:
        """Store updated device state and notify listeners."""
        self._states[device_id] = state
        self.async_set_updated_data(self._states.copy())

    def _merge_device_state(
        self, device_id: str, event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge event data into cached state for non-TH devices."""
        existing_state = self._states.get(device_id, {})
        new_state = self._sanitize_state_payload({**existing_state, **event_data})

        merged_nested_state = self._merge_nested_state(
            existing_state.get("state"),
            event_data.get("state"),
        )
        if merged_nested_state is not None:
            new_state["state"] = self._sanitize_nested_state(merged_nested_state)

        return new_state

    def _merge_thsensor_state(
        self, device_id: str, event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge TH sensor events while preserving API-only diagnostic fields."""
        existing_state = self._states.get(device_id, {})
        new_state = self._sanitize_state_payload({**existing_state, **event_data})

        merged_state_obj = self._build_thsensor_nested_state(existing_state, event_data)
        if merged_state_obj:
            new_state["state"] = self._sanitize_nested_state(merged_state_obj)

        return new_state

    def _build_thsensor_nested_state(
        self,
        existing_state: dict[str, Any],
        event_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the nested TH sensor state object from cached and event data."""
        merged_state_obj: dict[str, Any] = {}

        existing_nested_state = existing_state.get("state")
        if isinstance(existing_nested_state, dict):
            merged_state_obj.update(existing_nested_state)

        merged_nested_state = self._merge_nested_state(
            existing_nested_state,
            event_data.get("state"),
        )
        if isinstance(merged_nested_state, dict):
            merged_state_obj.update(merged_nested_state)
        elif merged_nested_state is not None:
            merged_state_obj["state"] = merged_nested_state

        # TH reports often publish flat keys at top-level (temperature, humidity, mode...)
        # Fold them into nested state while keeping top-level copies for fallback readers.
        for key, value in event_data.items():
            if key in {"state", "online", "reportAt", "lastReportedAt"}:
                continue
            if value is None and key in {"temperature", "humidity", "mode", "version"}:
                continue
            merged_state_obj[key] = value

        return merged_state_obj

    def _sanitize_state_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        """Remove inaccurate fields from a state payload."""
        sanitized = dict(state)
        sanitized.pop("batteryType", None)
        nested_state = sanitized.get("state")
        if isinstance(nested_state, dict):
            sanitized["state"] = self._sanitize_nested_state(nested_state)
        return sanitized

    def _sanitize_nested_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Remove inaccurate fields from a nested state object."""
        sanitized = dict(state)
        sanitized.pop("batteryType", None)
        return sanitized

    def _merge_nested_state(
        self,
        existing_state: Any,
        event_state: Any,
    ) -> Any | None:
        """Merge the payload's nested `state` field while preserving prior details."""
        if event_state is None:
            return None
        if isinstance(event_state, dict):
            if isinstance(existing_state, dict):
                return {**existing_state, **event_state}
            return event_state
        if isinstance(existing_state, dict):
            return {**existing_state, "state": event_state}
        return event_state

    @callback
    def _on_mqtt_disconnect(self) -> None:
        """Reconnect MQTT when the broker disconnects."""
        if self._shutdown:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = self.hass.async_create_task(self._async_reconnect_mqtt())

    async def _async_reconnect_mqtt(self) -> None:
        """Reconnect the MQTT client with backoff and a refreshed token."""
        backoff_seconds = 5
        while not self._shutdown:
            try:
                if self._mqtt_client:
                    await self._mqtt_client.disconnect()
                    self._mqtt_client = None
                await self._connect_mqtt()
                if self._mqtt_client is not None:
                    return
            except Exception:
                _LOGGER.exception("Failed to reconnect MQTT broker")

            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, 300)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Republish cached state so availability can age out silent devices."""
        return self._states.copy()

    def get_state(self, device_id: str) -> dict[str, Any]:
        """Get the current state for a device."""
        return self._states.get(device_id, {})

    async def async_send_command(
        self, device_id: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a command to a device."""
        device = self._devices.get(device_id)
        if not device:
            raise ValueError(f"Unknown device: {device_id}")
        return await self._client.set_state(device, params)


async def create_coordinator(
    hass: HomeAssistant,
    host: str,
    client_id: str,
    client_secret: str,
    net_id: str,
    http_port: int = 1080,
    mqtt_port: int = 18080,
) -> YoLocalCoordinator:
    """Create and initialize a coordinator.

    Returns a fully-initialized, connected coordinator ready for use.

    Raises:
        AuthenticationError: If credentials are invalid.
        Exception: If setup fails.
    """
    session = aiohttp.ClientSession()
    try:
        token_manager = TokenManager(host, client_id, client_secret, session, http_port)
        await token_manager.get_token()

        client = YoLinkClient(host, token_manager, session, http_port)

        coordinator = YoLocalCoordinator(
            hass, client, token_manager, session, net_id, mqtt_port
        )
        await coordinator._async_setup()

        return coordinator
    except Exception:
        await session.close()
        raise
