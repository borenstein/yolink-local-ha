"""Authentication and token management."""

from __future__ import annotations

import time

import aiohttp


class AuthenticationError(Exception):
    """Raised when authentication fails."""


class TokenManager:
    """Handles OAuth token acquisition and refresh."""

    # Refresh token 5 minutes before expiry
    REFRESH_BUFFER_SECONDS = 300

    def __init__(
        self,
        host: str,
        client_id: str,
        client_secret: str,
        session: aiohttp.ClientSession,
        port: int = 1080,
    ) -> None:
        """Initialize the token manager."""
        self._host = host
        self._port = port
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = session
        self._token: str | None = None
        self._expires_at: float = 0

    @property
    def base_url(self) -> str:
        """Return the base URL for the hub."""
        return f"http://{self._host}:{self._port}"

    @property
    def client_id(self) -> str:
        """Return the client ID (needed for MQTT auth)."""
        return self._client_id

    async def get_token(self) -> str:
        """Return a valid token, refreshing if needed."""
        if self._is_expired():
            await self._refresh()
        if self._token is None:
            raise AuthenticationError("No token available")
        return self._token

    def _is_expired(self) -> bool:
        """Check if the token is expired or about to expire."""
        if self._token is None:
            return True
        return time.time() >= (self._expires_at - self.REFRESH_BUFFER_SECONDS)

    async def _refresh(self) -> None:
        """Obtain a new token from the hub."""
        url = f"{self.base_url}/open/yolink/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        async with self._session.post(url, data=data) as resp:
            resp.raise_for_status()
            result = await resp.json()

        if "access_token" not in result:
            raise AuthenticationError(f"Auth failed: {result}")

        self._token = result["access_token"]
        # Token expires_in is in seconds
        expires_in = result.get("expires_in", 7200)
        self._expires_at = time.time() + expires_in

