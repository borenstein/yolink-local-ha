"""Config flow for YoLink Local integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from yolocal.api import AuthenticationError, create_client
from yolocal.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_HUB_IP,
    CONF_NET_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HUB_IP): str,
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Required(CONF_NET_ID): str,
    }
)


class YoLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for YoLink Local."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                client, _, session = await create_client(
                    host=user_input[CONF_HUB_IP],
                    client_id=user_input[CONF_CLIENT_ID],
                    client_secret=user_input[CONF_CLIENT_SECRET],
                )
                await session.close()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"YoLink Hub ({user_input[CONF_HUB_IP]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

