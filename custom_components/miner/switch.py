"""Support for miner active-state control."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add switch entities for the config entry."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    await coordinator.async_config_entry_first_refresh()
    if coordinator.backend and coordinator.backend.capabilities.pause_resume:
        async_add_entities([MinerActiveSwitch(coordinator=coordinator)])


class MinerActiveSwitch(MinerEntity, SwitchEntity):
    """Pause and resume mining through the selected backend."""

    def __init__(self, coordinator: MinerCoordinator) -> None:
        """Initialize the active-state switch."""
        super().__init__(coordinator=coordinator)
        identity = self.coordinator.data.get("mac") or self.coordinator.data.get("ip")
        self._attr_unique_id = f"{identity}-active" if identity else None
        self._attr_is_on = self.coordinator.data.get("is_mining")

    @property
    def name(self) -> str | None:
        """Return entity name."""
        return f"{self.coordinator.config_entry.title} active"

    async def async_turn_on(self) -> None:
        """Resume mining and then refresh actual state."""
        backend = self.coordinator.backend
        if backend is None:
            raise RuntimeError("Miner backend is not available")

        _LOGGER.debug(
            "%s: resume mining through %s backend",
            self.coordinator.config_entry.title,
            backend.kind.value,
        )
        await backend.async_resume()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Pause mining and then refresh actual state."""
        backend = self.coordinator.backend
        if backend is None:
            raise RuntimeError("Miner backend is not available")

        _LOGGER.debug(
            "%s: pause mining through %s backend",
            self.coordinator.config_entry.title,
            backend.kind.value,
        )
        await backend.async_pause()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update state only from confirmed backend telemetry."""
        is_mining = self.coordinator.data.get("is_mining")
        if is_mining is not None:
            self._attr_is_on = is_mining
        super()._handle_coordinator_update()
