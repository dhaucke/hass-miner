"""The Miner integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_MAX_POWER
from .const import CONF_MIN_POWER
from .const import DOMAIN

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BUTTON,
]


async def _async_update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Reload an entry after advanced options change."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy hass-miner config entries without breaking entities."""
    if entry.version < 2:
        data = dict(entry.data)
        options = dict(entry.options)

        # Version 1 exposed generic min/max power values during onboarding.
        # Version 2 keeps them as advanced options. Preserve user-defined
        # values, while leaving credentials and the host untouched.
        for key in (CONF_MIN_POWER, CONF_MAX_POWER):
            if key in data and key not in options:
                options[key] = data[key]
            data.pop(key, None)

        hass.config_entries.async_update_entry(
            entry,
            data=data,
            options=options,
            version=2,
            minor_version=0,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Miner from a config entry."""
    from .coordinator import MinerCoordinator
    from .services import async_setup_services

    coordinator = MinerCoordinator(hass, config_entry)
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator

    # The coordinator owns discovery, backend creation and connection errors.
    # Home Assistant installs manifest requirements before this code runs, so
    # the integration must never mutate its Python environment at runtime.
    await coordinator.async_config_entry_first_refresh()

    config_entry.async_on_unload(
        config_entry.add_update_listener(_async_update_listener)
    )
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    await async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id, None)
    return unload_ok
