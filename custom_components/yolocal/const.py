"""Constants for the YoLink Local integration."""

from homeassistant.const import UnitOfVolume

DOMAIN = "yolocal"

# Configuration keys
CONF_HUB_IP = "hub_ip"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_NET_ID = "net_id"

# Default ports
DEFAULT_HTTP_PORT = 1080
DEFAULT_MQTT_PORT = 18080

# API endpoints
TOKEN_ENDPOINT = "/open/yolink/token"
API_ENDPOINT = "/open/yolink/v2/api"

# Platforms we support
PLATFORMS: list[str] = [
    "sensor",
    "binary_sensor",
    "lock",
    "switch",
    "siren",
    "valve",
]

# Water meter unit mapping (data.attributes.meterUnit)
# 0=GAL, 1=CCF (hundred cubic feet), 2=m3, 3=L
WATER_METER_UNITS: dict[int, str] = {
    0: UnitOfVolume.GALLONS,
    1: UnitOfVolume.CUBIC_FEET,
    2: UnitOfVolume.CUBIC_METERS,
    3: UnitOfVolume.LITERS,
}

