"""Maintenance buttons for the Miner integration."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.components.sensor import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity

BUTTON_DESCRIPTIONS = {
    "reboot": ButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        entity_category=EntityCategory.CONFIG,
    ),
    "restart_backend": ButtonEntityDescription(
        key="restart_backend",
        translation_key="restart_backend",
        entity_category=EntityCategory.CONFIG,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add maintenance buttons supported by the selected backend."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.async_config_entry_first_refresh()

    backend = coordinator.backend
    if backend is None:
        return

    entities: list[ButtonEntity] = []
    if backend.capabilities.reboot:
        entities.append(
            MinerCommandButton(
                coordinator,
                BUTTON_DESCRIPTIONS["reboot"],
                backend.async_reboot,
            )
        )
    if backend.capabilities.restart_backend:
        entities.append(
            MinerCommandButton(
                coordinator,
                BUTTON_DESCRIPTIONS["restart_backend"],
                backend.async_restart_backend,
            )
        )

    async_add_entities(entities)


class MinerCommandButton(MinerEntity, ButtonEntity):
    """Button that executes a backend command and refreshes confirmed state."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        description: ButtonEntityDescription,
        command: Callable[[], Awaitable[None]],
    ) -> None:
        """Initialize a maintenance button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._command = command
        identity = coordinator.data.get("mac") or coordinator.data.get("ip")
        self._attr_unique_id = (
            f"{identity}-{description.key}" if identity is not None else None
        )

    async def async_press(self) -> None:
        """Execute the backend command and refresh miner state."""
        await self._command()
        await self.coordinator.async_request_refresh()
