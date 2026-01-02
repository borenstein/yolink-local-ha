"""YoLink Local integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_HUB_IP,
    CONF_NET_ID,
    DEFAULT_HTTP_PORT,
    DEFAULT_MQTT_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import YoLocalCoordinator, create_coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up YoLink Local from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    try:
        coordinator = await create_coordinator(
            hass=hass,
            host=entry.data[CONF_HUB_IP],
            client_id=entry.data[CONF_CLIENT_ID],
            client_secret=entry.data[CONF_CLIENT_SECRET],
            net_id=entry.data[CONF_NET_ID],
            http_port=DEFAULT_HTTP_PORT,
            mqtt_port=DEFAULT_MQTT_PORT,
        )
    except Exception:
        _LOGGER.exception("Failed to set up YoLink Local")
        return False

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: YoLocalCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
