"""Switch platform for EG-PM2-LAN — one SwitchEntity per socket."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_IP, DOMAIN, NUMBER_OF_SOCKETS
from .coordinator import EGPMCoordinator

_SOCKET_DESCRIPTIONS = [
    SwitchEntityDescription(
        key=f"socket_{i}",
        name=f"Socket {i}",
        icon="mdi:power-socket-eu",
    )
    for i in range(1, NUMBER_OF_SOCKETS + 1)
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 4 switch entities from a config entry."""
    coordinator: EGPMCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EGPMSwitch(coordinator, entry, desc, socket_nr=i + 1)
        for i, desc in enumerate(_SOCKET_DESCRIPTIONS)
    )


class EGPMSwitch(CoordinatorEntity[EGPMCoordinator], SwitchEntity):
    """One switchable socket of the EG-PM2-LAN."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EGPMCoordinator,
        entry: ConfigEntry,
        description: SwitchEntityDescription,
        socket_nr: int,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._socket_nr = socket_nr
        self._attr_unique_id = f"{entry.entry_id}_socket_{socket_nr}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Energenie EG-PM2-LAN",
            manufacturer="Gembird / Energenie",
            model="EG-PM2-LAN",
            configuration_url=f"http://{entry.data[CONF_IP]}/",
        )

    @property
    def is_on(self) -> bool | None:
        """Return current state from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._socket_nr)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_switch_socket(self._socket_nr, turn_on=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_switch_socket(self._socket_nr, turn_on=False)
