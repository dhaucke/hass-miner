"""Home Assistant services for Miner."""
from __future__ import annotations

import asyncio

from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

from .const import DOMAIN
from .const import SERVICE_REBOOT
from .const import SERVICE_RESTART_BACKEND
from .const import SERVICE_SET_WORK_MODE


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    def get_backends(call: ServiceCall):
        """Resolve selected devices to active miner backends."""
        device_ids = call.data.get(CONF_DEVICE_ID, [])
        if not device_ids:
            return []

        registry = async_get_device_registry(hass)
        backends = []
        for device_id in device_ids:
            device = registry.async_get(device_id)
            if device is None or device.primary_config_entry is None:
                continue
            coordinator = hass.data[DOMAIN].get(device.primary_config_entry)
            if coordinator is not None and coordinator.backend is not None:
                backends.append(coordinator.backend)
        return backends

    async def reboot(call: ServiceCall) -> None:
        """Reboot selected miners through their backend."""
        backends = get_backends(call)
        if backends:
            await asyncio.gather(*(backend.async_reboot() for backend in backends))

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, reboot)

    async def restart_backend(call: ServiceCall) -> None:
        """Restart the mining backend on selected devices."""
        backends = get_backends(call)
        if backends:
            await asyncio.gather(
                *(backend.async_restart_backend() for backend in backends)
            )

    hass.services.async_register(DOMAIN, SERVICE_RESTART_BACKEND, restart_backend)

    async def set_work_mode(call: ServiceCall) -> None:
        """Set a firmware-defined power mode on selected miners."""
        backends = get_backends(call)
        if backends:
            mode = call.data["mode"]
            await asyncio.gather(
                *(backend.async_set_power_mode(mode) for backend in backends)
            )

    hass.services.async_register(DOMAIN, SERVICE_SET_WORK_MODE, set_work_mode)
