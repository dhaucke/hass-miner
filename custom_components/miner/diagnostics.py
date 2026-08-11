"""Diagnostics support for the Miner integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import MinerCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, object]:
    """Return sanitized diagnostics for a miner config entry."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]

    if coordinator.backend is None:
        await coordinator.get_miner()

    backend_data: dict[str, object] = {}
    if coordinator.backend is not None:
        backend_data = await coordinator.backend.async_diagnostics()

    return {
        "entry": {
            "title": entry.title,
            "domain": entry.domain,
        },
        "backend": backend_data,
        "last_update_success": coordinator.last_update_success,
        "failure_count": coordinator._failure_count,
    }
