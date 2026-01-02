# YoLink Local

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant integration for YoLink devices using the **Local API** — no cloud required.

This integration communicates directly with your YoLink Local Hub over your LAN using HTTP and MQTT, providing fast, reliable, and private control of your YoLink devices.

## ⚠️ Disclaimer

**USE AT YOUR OWN RISK.** This software controls physical devices in your home, including locks, sirens, and other security-related equipment. The author assumes no responsibility for:

- Unauthorized access to your home
- False alarms or failure to alarm
- Property damage or personal injury
- Any other damages arising from the use of this software

By installing this integration, you acknowledge that you understand these risks and accept full responsibility for the security and safety of your home and its occupants. This software is provided "as is" without warranty of any kind.

**If you are not comfortable with these risks, do not use this software.**

## Why Use This Instead of Matter?

The YoLink Local Hub supports both Matter and a native Local API. While Matter works, the Local API offers:

- **Full device information** — temperature, humidity, battery levels, signal strength
- **Faster response times** — direct HTTP/MQTT vs Matter's abstraction layer
- **Richer entity types** — sensors, binary sensors, switches, locks, sirens all with proper device classes

## Supported Devices

| Device Type | Entity Type | Features |
|-------------|-------------|----------|
| THSensor | Sensor | Temperature, humidity, battery |
| DoorSensor | Binary Sensor | Open/closed state, battery |
| LeakSensor | Binary Sensor | Leak detected, battery |
| Outlet | Switch | On/off control |
| Lock | Lock | Lock/unlock control |
| Siren | Siren | Trigger/stop alarm |

Additional device types can be added — contributions welcome!

## Prerequisites

Before installing this integration, you need:

1. A **YoLink Local Hub** (model YS1606-UC)
2. The hub connected to your network via Ethernet or Wi-Fi
3. Devices migrated from YoLink Cloud to the Local Hub
4. HTTP and MQTT protocols enabled on the hub

For detailed setup instructions, see the excellent [YoLink Local Hub Setup Guide](https://community.home-assistant.io/t/yolink-local-hub-matter-integration-guide/911359) on the Home Assistant Community forums.

## Finding Your Credentials

You'll need four pieces of information from the YoLink app:

### Hub IP Address

1. Open the YoLink app
2. Tap on your **YoLink Local Hub** device
3. Tap the **⋮** menu (top right)
4. Find the **IP Address** under the Ethernet section

![Hub main screen](images/IMG_2021.PNG)

![Hub details showing IP address](images/IMG_2022.PNG)

### Client ID, Client Secret, and Net ID

1. From the hub screen, tap **Local Network**
2. Go to the **Integrations** tab for Client ID and Client Secret
3. Go to the **General** tab for Net ID

![Integrations tab with API credentials](images/IMG_2023.PNG)

![General tab with Net ID](images/IMG_2024.PNG)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the **⋮** menu → **Custom repositories**
3. Add `https://github.com/dbborens/yolink-local-ha` with category **Integration**
4. Search for "YoLink Local" and install
5. Restart Home Assistant

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/yolocal` folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **YoLink Local**
4. Enter your credentials:
   - **Hub IP**: Your hub's IP address
   - **Client ID**: From the Integrations tab
   - **Client Secret**: From the Integrations tab  
   - **Net ID**: From the General tab

## How It Works

- **Device Discovery**: On startup, the integration queries the hub for all connected devices
- **Initial State**: Each device's current state is fetched via HTTP
- **Real-time Updates**: MQTT subscription receives instant state changes (door opens, temperature changes, etc.)
- **Commands**: Lock/unlock, on/off, and other commands are sent via HTTP

## Troubleshooting

### Integration doesn't appear after restart

Check the Home Assistant logs for import errors. The integration requires `paho-mqtt>=2.0.0`.

### Devices show as unavailable

- Verify the hub IP address is correct and reachable
- Check that HTTP (port 1080) and MQTT (port 18080) are enabled on the hub
- Ensure devices have been migrated to the Local Network in the YoLink app

### State updates are delayed

Real-time updates require MQTT. If updates only happen on HA restart, check that:
- MQTT is enabled on the hub (port 18080)
- Your firewall allows the connection

## Contributing

Contributions are welcome! To add support for additional device types:

1. Check the [YoLink Local API documentation](https://doc.yosmart.com/docs/protocol/local_hub/localHubMethods)
2. Add the device type to the appropriate platform file
3. Submit a pull request

## Did I use an AI tool to build this in two hours?

Hell yes I did!

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.

## Credits

- [YoLink](https://www.yosmart.com/) for the Local Hub and API
- The Home Assistant community for testing and feedback
