"""Diagnostics support for the Miner integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import MinerCoordinator

_REDACTED = "**REDACTED**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, object]:
    """Return sanitized diagnostics for a miner config entry."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]

    if coordinator.backend is None:
        await coordinator.get_miner()

    backend_data: dict[str, object] = {}
    if coordinator.backend is not None:
        backend_data = dict(await coordinator.backend.async_diagnostics())

    # Network location and local hostnames are useful during live debugging but
    # should not be included by default in a file users may attach publicly.
    for key in ("host", "hostname", "ip", "mac"):
        if key in backend_data and backend_data[key] is not None:
            backend_data[key] = _REDACTED

    return {
        "entry": {
            "title": entry.title,
            "domain": entry.domain,
            "version": entry.version,
            "minor_version": entry.minor_version,
        },
        "backend": backend_data,
        "last_update_success": coordinator.last_update_success,
        "failure_count": coordinator._failure_count,
    }
