"""Data coordinator for YoLink Local integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
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
from .api.auth import AuthenticationError

_LOGGER = logging.getLogger(__name__)

# Polling interval as fallback when MQTT events are missed
UPDATE_INTERVAL = timedelta(minutes=5)


def _deep_merge_state(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge an incoming event into existing device state (one level deep).

    WaterMeterController reports ``state`` as a nested object
    (``state.valve``, ``state.meter``, ``state.waterFlowing``). A partial
    event (e.g. a ``setState`` response carrying only ``state.valve``) must
    not replace the whole ``state`` object and wipe out the meter reading,
    so dict-valued keys are merged recursively one level deep.
    """
    merged: dict[str, Any] = dict(existing)
    for key, value in incoming.items():
        prev = merged.get(key)
        if isinstance(prev, dict) and isinstance(value, dict):
            merged[key] = {**prev, **value}
        else:
            merged[key] = value
    return merged


class YoLocalCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator for YoLink Local devices.

    Manages MQTT subscription for real-time updates and provides
    device state to entities. Falls back to HTTP polling every 5 minutes
    to ensure state stays current if MQTT events are missed.
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
            update_interval=UPDATE_INTERVAL,
        )
        self._client = client
        self._token_manager = token_manager
        self._session = session
        self._net_id = net_id
        self._mqtt_port = mqtt_port
        self._mqtt_client: YoLinkMQTTClient | None = None
        self._devices: dict[str, Device] = {}
        self._states: dict[str, dict[str, Any]] = {}

    @property
    def devices(self) -> dict[str, Device]:
        """Return the device registry."""
        return self._devices

    async def _async_setup(self) -> None:
        """Set up the coordinator: fetch devices and connect MQTT."""
        devices = await self._client.get_devices()
        self._devices = {d.device_id: d for d in devices}

        await self._fetch_all_states()
        await self._connect_mqtt()

    async def _fetch_all_states(self) -> None:
        """Fetch current state for all devices via HTTP API."""
        for device in self._devices.values():
            try:
                state = await self._client.get_state(device)
                self._states[device.device_id] = state
            except Exception:
                _LOGGER.warning("Failed to get state for %s", device.name)
                self._states.setdefault(device.device_id, {})

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Poll device states via HTTP as a fallback.

        This runs periodically (every 5 minutes) to ensure state stays
        current even if MQTT events are missed or the connection drops.
        """
        await self._fetch_all_states()
        return self._states.copy()

    async def async_shutdown(self) -> None:
        """Shut down the coordinator."""
        if self._mqtt_client:
            await self._mqtt_client.disconnect()
            self._mqtt_client = None
        await self._session.close()

    async def _connect_mqtt(self) -> None:
        """Connect to MQTT broker."""
        token = await self._token_manager.get_token()
        host = self._client.host

        self._mqtt_client = YoLinkMQTTClient(
            host=host,
            net_id=self._net_id,
            client_id=self._token_manager.client_id,
            access_token=token,
            port=self._mqtt_port,
        )
        self._mqtt_client.subscribe(self._on_device_event)

        try:
            await self._mqtt_client.connect()
            _LOGGER.info("Connected to YoLink MQTT broker")
        except Exception:
            _LOGGER.exception("Failed to connect to MQTT broker")

    @callback
    def _on_device_event(self, event: DeviceEvent) -> None:
        """Handle a device event from MQTT.

        Merges incoming event data with the existing device state so that
        partial events (e.g. connectivity-only updates) don't wipe out
        previously known sensor readings like temperature and humidity.
        """
        device_id = event.device_id
        if device_id not in self._devices:
            _LOGGER.debug("Ignoring event for unknown device: %s", device_id)
            return

        existing = self._states.get(device_id, {})
        self._states[device_id] = _deep_merge_state(existing, event.data)
        self.async_set_updated_data(self._states.copy())

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

