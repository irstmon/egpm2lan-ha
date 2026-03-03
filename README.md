# Energenie EG-PM2-LAN — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![HA Version](https://img.shields.io/badge/HA-2026.2%2B-blue)

Native Home Assistant integration for the **Gembird / Energenie EG-PM2-LAN**
network-controlled power strip (4 switchable sockets).

## Why this exists

The EG-PM2-LAN supports **only one HTTP session at a time**. If a second
request arrives while a session is open, the device locks up and requires
a power cycle. This integration solves that with an internal **asyncio queue
daemon** that strictly serializes all device communication:
```
Every operation:  Login → [Switch command] → Read all 4 states → Logout
```

No concurrent sessions are ever possible, regardless of how many automations
or UI interactions trigger switches simultaneously.

## Features

- ✅ 4 switch entities (one per socket)
- ✅ All 4 socket states read in a single request
- ✅ Strict session serialization — device never locks up
- ✅ Immediate state update after switching (no waiting for next poll)
- ✅ Configurable poll interval (default 30 s)
- ✅ UI-based setup via Config Flow (no YAML needed)
- ✅ Works with both old and new device firmware
- ✅ German + English UI

## Installation via HACS

1. In HACS → **Integrations** → ⋮ menu → **Custom repositories**
2. Add `https://github.com/irstmon/egpm2lan-ha` as type **Integration**
3. Install **Energenie EG-PM2-LAN**
4. Restart Home Assistant

## Manual Installation

Copy the `custom_components/egpm2lan/` folder into your
`<config>/custom_components/` directory and restart HA.

## Configuration

1. **Settings → Devices & Services → Add Integration**
2. Search for **Energenie EG-PM2-LAN**
3. Enter IP address and password (if set on the device)
4. 4 switch entities are created automatically

## Device Notes

- The device web interface must not be open in a browser during operation
- Default password is usually empty or `1234` depending on firmware version
- Tested with firmware that exposes `sockstates` JavaScript variable
- Legacy firmware using bare `0,1,0,1` HTML pattern is also supported

## Migration from command_line switches

Remove your `command_line` entries from `configuration.yaml` and
`custom_command_line.yaml`. After installing this integration, the old
`energenie_steckdose_1..4` entities will be replaced by
`switch.energenie_eg_pm2_lan_socket_1..4`.

To keep your existing automations working, add these to your `configuration.yaml`:
```yaml
homeassistant:
  customize:
    switch.energenie_eg_pm2_lan_socket_1:
      friendly_name: "Energenie Steckdose 1"
```

## License

MIT