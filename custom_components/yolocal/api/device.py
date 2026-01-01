"""Device data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Device:
    """Represents a YoLink device."""

    device_id: str
    name: str
    token: str
    device_type: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Device:
        """Create a Device from API response data."""
        return cls(
            device_id=data["deviceId"],
            name=data["name"],
            token=data["token"],
            device_type=data["type"],
        )

