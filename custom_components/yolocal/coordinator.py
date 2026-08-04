"""Data coordinator for YoLink Local integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    Device,
    DeviceEvent,
    TokenManager,
    YoLinkClient,
    YoLinkMQTTClient,
)

_LOGGER = logging.getLogger(__name__)

# Polling interval as fallback when MQTT events are missed
UPDATE_INTERVAL = timedelta(minutes=5)

# A device is offline if it hasn't reported within this window. Battery
# devices heartbeat only every ~4 hours, so this allows two missed
# heartbeats plus margin (same value as YOLINK_OFFLINE_TIME in HA core's
# cloud yolink integration).
OFFLINE_TIME = timedelta(seconds=32400)


def _merge_device_state(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    """Merge an MQTT event payload into the cached device state.

    Keys merge shallowly with incoming values winning. Special case: when the
    cached ``state`` is a nested dict but the event carries a flat scalar
    ``state`` (e.g. ``MotionSensor.Alert`` sends ``{"state": "alert"}`` while
    ``getState`` reports ``{"state": {"state": ..., "battery": ...}}``), fold
    the scalar into the existing dict so sibling fields such as ``battery`` and
    ``devTemperature`` are preserved instead of clobbered.
    """
    if isinstance(existing.get("state"), dict) and isinstance(incoming.get("state"), str):
        return {
            **existing,
            **incoming,
            "state": {**existing["state"], "state": incoming["state"]},
        }
    return {**existing, **incoming}


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
        self._online: dict[str, bool] = {}

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
        """Fetch current state for all devices via HTTP API.

        A single device failing is tolerated (sleepy devices can miss a
        poll), but if every device fails the hub itself is unreachable and
        UpdateFailed is raised so entities go unavailable.
        """
        failures = 0
        for device in self._devices.values():
            try:
                state = await self._client.get_state(device)
            except Exception:
                _LOGGER.warning("Failed to get state for %s", device.name)
                self._states.setdefault(device.device_id, {})
                failures += 1
                continue
            self._states[device.device_id] = state
            self._update_online_from_report(device.device_id, state)
        if self._devices and failures == len(self._devices):
            raise UpdateFailed("Could not fetch state for any device")

    def _update_online_from_report(
        self, device_id: str, state: dict[str, Any]
    ) -> None:
        """Derive online status from the device's last-report timestamp.

        The hub's ``online`` flag reads false between the ~4 h heartbeats
        of sleepy battery devices, so it can't be trusted directly. A
        device is online if it reported within OFFLINE_TIME; a state
        without a parseable ``reportAt`` leaves the previous judgment
        unchanged.
        """
        report_at = state.get("reportAt")
        if not isinstance(report_at, str):
            return
        reported = dt_util.parse_datetime(report_at)
        if reported is None:
            return
        if reported.tzinfo is None:
            reported = reported.replace(tzinfo=dt_util.UTC)
        self._online[device_id] = dt_util.utcnow() - reported < OFFLINE_TIME

    def is_online(self, device_id: str) -> bool:
        """Return whether a device is considered online."""
        return self._online.get(device_id, True)

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
        self._states[device_id] = _merge_device_state(existing, event.data)
        # Any message from the device proves it's alive, regardless of what
        # the last poll said.
        self._online[device_id] = True
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

