"""Energenie EG-PM2-LAN - Home Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_INTER_OP_DELAY,
    CONF_IP,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_INTER_OP_DELAY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import EGPMCoordinator

PLATFORMS: list[Platform] = [Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EG-PM2-LAN from a config entry."""
    coordinator = EGPMCoordinator(
        hass,
        ip=entry.data[CONF_IP],
        password=entry.data.get(CONF_PASSWORD, ""),
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        inter_op_delay=entry.options.get(CONF_INTER_OP_DELAY, DEFAULT_INTER_OP_DELAY),
    )

    coordinator.start_daemon()

    # First status poll - raises ConfigEntryNotReady if device unreachable
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry and stop the daemon."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: EGPMCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.stop_daemon()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change (e.g. scan_interval or inter_op_delay)."""
    await hass.config_entries.async_reload(entry.entry_id)
