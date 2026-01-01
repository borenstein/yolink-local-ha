"""YoLink Local API client library.

This module contains pure Python code for communicating with the YoLink
Local Hub. It has no Home Assistant dependencies.
"""

from yolocal.api.auth import AuthenticationError, TokenManager
from yolocal.api.client import ApiError, YoLinkClient, create_client
from yolocal.api.device import Device
from yolocal.api.mqtt import DeviceEvent, YoLinkMQTTClient

__all__ = [
    "ApiError",
    "AuthenticationError",
    "Device",
    "DeviceEvent",
    "TokenManager",
    "YoLinkClient",
    "YoLinkMQTTClient",
    "create_client",
]
