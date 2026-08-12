"""Home Assistant services for Miner."""
from __future__ import annotations

import asyncio

from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

from .const import DOMAIN
from .const import SERVICE_REBOOT
from .const import SERVICE_RESTART_BACKEND
from .const import SERVICE_SET_WORK_MODE


def _normalize_device_ids(value) -> list[str]:
    """Normalize HA device selectors that may return one id or a list."""
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


async def _async_run_tracked(coordinator, action: str, coro) -> None:
    """Run one backend call, recording a command failure on the right coordinator."""
    try:
        await coro
    except HomeAssistantError as err:
        coordinator.record_command_failure()
        raise err
    except Exception as err:
        coordinator.record_command_failure()
        raise HomeAssistantError(f"Failed to {action}: {err}") from err


async def _async_gather_backend_calls(action: str, coordinators, make_coro) -> None:
    """Run one backend call per coordinator in parallel, tracking failures."""
    try:
        await asyncio.gather(
            *(
                _async_run_tracked(coordinator, action, make_coro(coordinator.backend))
                for coordinator in coordinators
            )
        )
    except HomeAssistantError:
        raise
    except Exception as err:
        raise HomeAssistantError(f"Failed to {action}: {err}") from err


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services once per Home Assistant instance."""
    if hass.services.has_service(DOMAIN, SERVICE_REBOOT):
        return

    def get_coordinators(call: ServiceCall):
        """Resolve selected devices to active miner coordinators."""
        device_ids = _normalize_device_ids(call.data.get(CONF_DEVICE_ID))
        registry = async_get_device_registry(hass)
        coordinators = []
        for device_id in device_ids:
            device = registry.async_get(device_id)
            if device is None or device.primary_config_entry is None:
                continue
            coordinator = hass.data.get(DOMAIN, {}).get(device.primary_config_entry)
            if coordinator is not None and coordinator.backend is not None:
                coordinators.append(coordinator)
        return coordinators

    async def reboot(call: ServiceCall) -> None:
        """Reboot selected miners through their backend."""
        coordinators = get_coordinators(call)
        if coordinators:
            await _async_gather_backend_calls(
                "reboot miner", coordinators, lambda backend: backend.async_reboot()
            )

    async def restart_backend(call: ServiceCall) -> None:
        """Restart the mining backend on selected devices."""
        coordinators = get_coordinators(call)
        if coordinators:
            await _async_gather_backend_calls(
                "restart mining backend",
                coordinators,
                lambda backend: backend.async_restart_backend(),
            )

    async def set_work_mode(call: ServiceCall) -> None:
        """Set a firmware-defined power mode on selected miners."""
        coordinators = get_coordinators(call)
        if coordinators:
            mode = call.data["mode"]
            await _async_gather_backend_calls(
                "set work mode",
                coordinators,
                lambda backend: backend.async_set_power_mode(mode),
            )

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, reboot)
    hass.services.async_register(DOMAIN, SERVICE_RESTART_BACKEND, restart_backend)
    hass.services.async_register(DOMAIN, SERVICE_SET_WORK_MODE, set_work_mode)
