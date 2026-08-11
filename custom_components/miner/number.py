"""Support for miner power-limit controls."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.sensor import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity

_LOGGER = logging.getLogger(__name__)


NUMBER_DESCRIPTION_KEY_MAP: dict[str, NumberEntityDescription] = {
    "power_limit": NumberEntityDescription(
        key="Power Limit",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        entity_category=EntityCategory.CONFIG,
    )
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add number entities for a miner config entry."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    await coordinator.async_config_entry_first_refresh()
    if coordinator.backend and coordinator.backend.capabilities.power_limit:
        async_add_entities(
            [
                MinerPowerLimitNumber(
                    coordinator=coordinator,
                    entity_description=NUMBER_DESCRIPTION_KEY_MAP["power_limit"],
                )
            ]
        )


class MinerPowerLimitNumber(MinerEntity, NumberEntity):
    """Number entity used to set the miner power limit."""

    def __init__(
        self, coordinator: MinerCoordinator, entity_description: NumberEntityDescription
    ) -> None:
        """Initialize the power-limit entity."""
        super().__init__(coordinator=coordinator)
        self.entity_description = entity_description
        self._attr_native_value = self.coordinator.data["miner_sensors"]["power_limit"]

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        return f"{self.coordinator.config_entry.title} Power Limit"

    @property
    def unique_id(self) -> str | None:
        """Return the stable entity UUID."""
        identity = self.coordinator.data.get("mac") or self.coordinator.data.get("ip")
        return f"{identity}-power_limit" if identity else None

    @property
    def native_min_value(self) -> float | None:
        """Return the backend-supported minimum value."""
        return self.coordinator.data["power_limit_range"]["min"]

    @property
    def native_max_value(self) -> float | None:
        """Return the backend-supported maximum value."""
        return self.coordinator.data["power_limit_range"]["max"]

    @property
    def native_step(self) -> float | None:
        """Return the backend-supported increment."""
        return self.coordinator.data["power_limit_range"].get("step", 100)

    async def async_set_native_value(self, value: float) -> None:
        """Set the miner power limit through the active backend."""
        backend = self.coordinator.backend
        if backend is None:
            raise RuntimeError("Miner backend is not available")

        requested = int(value)
        _LOGGER.debug(
            "%s: setting power limit to %s W through %s backend",
            self.coordinator.config_entry.title,
            requested,
            backend.kind.value,
        )
        await backend.async_set_power_limit(requested)
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        value = self.coordinator.data["miner_sensors"]["power_limit"]
        if value is not None:
            self._attr_native_value = value
        super()._handle_coordinator_update()
