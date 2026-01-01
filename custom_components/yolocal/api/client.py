"""HTTP client for YoLink Local Hub API."""

from __future__ import annotations

from typing import Any

import aiohttp

from yolocal.api.auth import AuthenticationError, TokenManager
from yolocal.api.device import Device


class ApiError(Exception):
    """Raised when an API call fails."""


class YoLinkClient:
    """HTTP client for YoLink Local Hub."""

    def __init__(
        self,
        host: str,
        token_manager: TokenManager,
        session: aiohttp.ClientSession,
        port: int = 1080,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._token_manager = token_manager
        self._session = session

    @property
    def host(self) -> str:
        """Return the hub host."""
        return self._host

    @property
    def base_url(self) -> str:
        """Return the base URL for the hub."""
        return f"http://{self._host}:{self._port}"

    async def get_devices(self) -> list[Device]:
        """Fetch the list of devices from the hub."""
        result = await self._request({"method": "Home.getDeviceList"})
        return [Device.from_api(d) for d in result.get("devices", [])]

    async def get_state(self, device: Device) -> dict[str, Any]:
        """Get the current state of a device."""
        return await self._request({
            "method": f"{device.device_type}.getState",
            "targetDevice": device.device_id,
            "token": device.token,
        })

    async def set_state(
        self, device: Device, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Set the state of a device."""
        return await self._request({
            "method": f"{device.device_type}.setState",
            "targetDevice": device.device_id,
            "token": device.token,
            "params": params,
        })

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Make an authenticated API request."""
        token = await self._token_manager.get_token()
        url = f"{self.base_url}/open/yolink/v2/api"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        async with self._session.post(url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            result = await resp.json()

        if result.get("code") != "000000":
            raise ApiError(f"API error: {result}")

        return result.get("data", {})


async def create_client(
    host: str,
    client_id: str,
    client_secret: str,
    port: int = 1080,
) -> tuple["YoLinkClient", TokenManager, aiohttp.ClientSession]:
    """Create an authenticated client.

    Returns the client, token manager, and session. Caller is responsible
    for closing the session when done.

    Raises:
        AuthenticationError: If credentials are invalid.
    """
    session = aiohttp.ClientSession()
    try:
        token_manager = TokenManager(host, client_id, client_secret, session, port)
        await token_manager.get_token()  # Validates credentials
        client = YoLinkClient(host, token_manager, session, port)
        return client, token_manager, session
    except Exception:
        await session.close()
        raise
