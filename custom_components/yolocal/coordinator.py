"""Data coordinator for YoLink Local integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import (
    Device,
    DeviceEvent,
    TokenManager,
    YoLinkClient,
    YoLinkMQTTClient,
)
from .const import DEVICE_DISCOVERY_INTERVAL, DOMAIN, STATE_REFRESH_INTERVAL

_LOGGER = logging.getLogger(__name__)
RECENT_REPORT_THRESHOLD_SECONDS = 10 * 60
type DeviceRegistryListener = Callable[[list[Device], list[Device]], None]


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
        config_entry_id: str,
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
        self._config_entry_id = config_entry_id
        self._net_id = net_id
        self._mqtt_port = mqtt_port
        self._mqtt_client: YoLinkMQTTClient | None = None
        self._devices: dict[str, Device] = {}
        self._states: dict[str, dict[str, Any]] = {}
        self._reconnect_task: asyncio.Task[None] | None = None
        self._discovery_task: asyncio.Task[None] | None = None
        self._device_registry_listeners: list[DeviceRegistryListener] = []
        self._shutdown = False

    @property
    def devices(self) -> dict[str, Device]:
        """Return the device registry."""
        return self._devices

    def register_device_registry_listener(
        self, listener: DeviceRegistryListener
    ) -> Callable[[], None]:
        """Subscribe to device registry changes."""
        self._device_registry_listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._device_registry_listeners:
                self._device_registry_listeners.remove(listener)

        return unsubscribe

    def _create_background_task(
        self,
        coro: Coroutine[Any, Any, Any],
        name: str,
    ) -> asyncio.Task[None] | Any:
        """Create a background task without blocking HA startup."""
        if hasattr(self.hass, "async_create_background_task"):
            return self.hass.async_create_background_task(coro, name)
        return self.hass.async_create_task(coro)

    async def _async_setup(self) -> None:
        """Set up the coordinator: fetch devices and connect MQTT."""
        devices = await self._client.get_devices()
        self._devices = {d.device_id: d for d in devices}
        self._remove_stale_registry_devices(set(self._devices))

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

        if self._discovery_task is None:
            self._discovery_task = self._create_background_task(
                self._async_device_discovery_loop(),
                "yolocal_device_discovery",
            )

        # Publish initial state through the coordinator so HA can treat this
        # instance as having current data and schedule future refreshes.
        self.async_set_updated_data(self._states.copy())

    async def async_shutdown(self) -> None:
        """Shut down the coordinator."""
        self._shutdown = True
        if self._discovery_task:
            self._discovery_task.cancel()
            self._discovery_task = None
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
        self._apply_event_availability(existing_state, event_data, new_state)

        merged_state_obj = self._build_device_nested_state(existing_state, event_data)
        if merged_state_obj:
            new_state["state"] = self._sanitize_nested_state(merged_state_obj)

        return new_state

    def _merge_thsensor_state(
        self, device_id: str, event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge TH sensor events while preserving API-only diagnostic fields."""
        existing_state = self._states.get(device_id, {})
        new_state = self._sanitize_state_payload({**existing_state, **event_data})
        self._apply_event_availability(existing_state, event_data, new_state)

        merged_state_obj = self._build_thsensor_nested_state(existing_state, event_data)
        if merged_state_obj:
            new_state["state"] = self._sanitize_nested_state(merged_state_obj)

        return new_state

    def _apply_event_availability(
        self,
        existing_state: dict[str, Any],
        event_data: dict[str, Any],
        merged_state: dict[str, Any],
    ) -> None:
        """Mark a device online again when a fresh report arrives."""
        if "online" in event_data:
            return

        reported_at = event_data.get("lastReportedAt")
        if reported_at and reported_at != existing_state.get("lastReportedAt"):
            merged_state["online"] = True

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

    def _build_device_nested_state(
        self,
        existing_state: dict[str, Any],
        event_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the nested state object for non-TH devices."""
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

        for key, value in event_data.items():
            if key in {"state", "online", "reportAt", "lastReportedAt"}:
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
        """Refresh device state from the hub and merge it into the cache."""
        refreshed_states = self._states.copy()
        now = dt_util.utcnow()

        for device_id, device in self._devices.items():
            cached_state = refreshed_states.get(device_id, {})
            report_at = cached_state.get("lastReportedAt")
            if report_at:
                try:
                    last_report = dt_util.parse_datetime(report_at)
                except Exception:
                    last_report = None
                if (
                    last_report is not None
                    and (now - last_report).total_seconds() < RECENT_REPORT_THRESHOLD_SECONDS
                ):
                    continue

            try:
                state = await self._client.get_state(device)
            except Exception:
                _LOGGER.warning("Failed to refresh state for %s", device.name)
                continue

            normalized_state = self._sanitize_state_payload(state)
            if (
                normalized_state.get("reportAt")
                and "lastReportedAt" not in normalized_state
            ):
                normalized_state["lastReportedAt"] = normalized_state["reportAt"]

            if device.device_type == "THSensor":
                refreshed_states[device_id] = self._merge_thsensor_state(
                    device_id,
                    normalized_state,
                )
            else:
                refreshed_states[device_id] = self._merge_device_state(
                    device_id,
                    normalized_state,
                )

        self._states = refreshed_states
        return refreshed_states.copy()

    async def _async_device_discovery_loop(self) -> None:
        """Periodically check for device additions/removals."""
        interval = DEVICE_DISCOVERY_INTERVAL.total_seconds()
        while not self._shutdown:
            await asyncio.sleep(interval)
            await self._async_refresh_devices()

    async def _async_refresh_devices(self) -> bool:
        """Refresh the device registry and notify listeners if membership changed."""
        try:
            devices = await self._client.get_devices()
        except Exception:
            _LOGGER.warning("Failed to refresh device list", exc_info=True)
            return False

        new_devices = {device.device_id: device for device in devices}
        if set(new_devices) == set(self._devices):
            self._devices = new_devices
            return False

        existing_device_ids = set(self._devices)
        added_ids = sorted(set(new_devices) - existing_device_ids)
        removed_ids = sorted(existing_device_ids - set(new_devices))
        added_devices = [new_devices[device_id] for device_id in added_ids]
        removed_devices = [self._devices[device_id] for device_id in removed_ids]
        _LOGGER.info(
            "Device registry changed; added=%s removed=%s.",
            added_ids,
            removed_ids,
        )
        self._devices = new_devices

        for device_id in removed_ids:
            self._states.pop(device_id, None)
            self._remove_device_from_registry(device_id)

        for device in added_devices:
            try:
                state = await self._client.get_state(device)
                state = self._sanitize_state_payload(state)
                if state.get("reportAt") and "lastReportedAt" not in state:
                    state["lastReportedAt"] = state["reportAt"]
                self._states[device.device_id] = state
            except Exception:
                _LOGGER.warning("Failed to get initial state for %s", device.name)
                self._states[device.device_id] = {}

        for listener in list(self._device_registry_listeners):
            try:
                listener(added_devices, removed_devices)
            except Exception:
                _LOGGER.exception("Device registry listener failed")

        self.async_set_updated_data(self._states.copy())

        return True

    def _remove_device_from_registry(self, device_id: str) -> None:
        """Remove a deleted device from the HA device registry."""
        self._remove_entity_registry_entries(device_id)
        registry = dr.async_get(self.hass)
        device_entry = registry.async_get_device(identifiers={(DOMAIN, device_id)})
        if device_entry is not None:
            registry.async_remove_device(device_entry.id)

    def _remove_stale_registry_devices(self, active_device_ids: set[str]) -> None:
        """Remove registry devices that no longer exist on the hub."""
        registry = dr.async_get(self.hass)
        if hasattr(dr, "async_entries_for_config_entry"):
            device_entries = dr.async_entries_for_config_entry(
                registry,
                self._config_entry_id,
            )
        else:
            device_entries = list(getattr(registry, "devices", {}).values())

        for entry in list(device_entries):
            normalized_identifiers = set(getattr(entry, "identifiers", set()))
            if len(normalized_identifiers) != 1:
                continue
            domain, device_id = next(iter(normalized_identifiers))
            if domain != DOMAIN or device_id in active_device_ids:
                continue
            self._remove_entity_registry_entries(device_id)
            registry.async_remove_device(entry.id)

    def _remove_entity_registry_entries(self, device_id: str) -> None:
        """Remove orphaned entity-registry entries for a missing device."""
        registry = er.async_get(self.hass)
        if hasattr(er, "async_entries_for_config_entry"):
            entity_entries = er.async_entries_for_config_entry(
                registry,
                self._config_entry_id,
            )
        else:
            entity_entries = list(getattr(registry, "entities", {}).values())

        for entry in list(entity_entries):
            entity_id = getattr(entry, "entity_id", None)
            unique_id = getattr(entry, "unique_id", None)
            if unique_id == device_id or (
                isinstance(unique_id, str) and unique_id.startswith(f"{device_id}_")
            ):
                if entity_id is not None:
                    registry.async_remove(entity_id)

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
    config_entry_id: str,
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
            hass, client, token_manager, session, config_entry_id, net_id, mqtt_port
        )
        await coordinator._async_setup()

        return coordinator
    except Exception:
        await session.close()
        raise
