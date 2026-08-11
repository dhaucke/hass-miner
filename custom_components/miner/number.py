"""Support for Bitcoin ASIC miners."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.sensor import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator

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
    if coordinator.miner.supports_autotuning:
        async_add_entities(
            [
                MinerPowerLimitNumber(
                    coordinator=coordinator,
                    entity_description=NUMBER_DESCRIPTION_KEY_MAP["power_limit"],
                )
            ]
        )


class MinerPowerLimitNumber(CoordinatorEntity[MinerCoordinator], NumberEntity):
    """Number entity used to set the miner power limit."""

    def __init__(
        self, coordinator: MinerCoordinator, entity_description: NumberEntityDescription
    ) -> None:
        """Initialize the power-limit entity."""
        super().__init__(coordinator=coordinator)
        self._attr_native_value = self.coordinator.data["miner_sensors"]["power_limit"]
        self.entity_description = entity_description

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} Power Limit"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            connections={
                ("ip", self.coordinator.data["ip"]),
                (
                    device_registry.CONNECTION_NETWORK_MAC,
                    self.coordinator.data["mac"],
                ),
            },
            configuration_url=f"http://{self.coordinator.data['ip']}",
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            sw_version=self.coordinator.data["fw_ver"],
            name=f"{self.coordinator.config_entry.title}",
        )

    @property
    def unique_id(self) -> str | None:
        """Return device UUID."""
        return f"{self.coordinator.data['mac']}-power_limit"

    @property
    def native_min_value(self) -> float | None:
        """Return device minimum value."""
        return self.coordinator.data["power_limit_range"]["min"]

    @property
    def native_max_value(self) -> float | None:
        """Return device maximum value."""
        return self.coordinator.data["power_limit_range"]["max"]

    @property
    def native_step(self) -> float | None:
        """Return device increment step."""
        return 100

    @property
    def native_unit_of_measurement(self):
        """Return device unit of measurement."""
        return "W"

    async def async_set_native_value(self, value):
        """Update the current value."""
        import pyasic  # lazy import to avoid blocking event loop

        miner = self.coordinator.miner

        _LOGGER.debug(
            "%s: setting power limit to %s.",
            self.coordinator.config_entry.title,
            value,
        )

        if not miner.supports_autotuning:
            raise TypeError(
                f"{self.coordinator.config_entry.title}: Tuning not supported."
            )

        # pyasic 0.78.8 rebuilds the complete /etc/bosminer.toml file when
        # BOSMiner.set_power_limit() is called. The [format].model value is
        # generated from miner.make and miner.raw_model. If either detection
        # value is temporarily missing, pyasic can write model = " ", after
        # which BOSminer refuses to start. Refuse the write instead of risking
        # a destructive configuration update. A dedicated Braiins backend will
        # replace this compatibility guard in a later refactor.
        if type(miner).__name__ == "BOSMiner":
            make = getattr(miner, "make", None)
            raw_model = getattr(miner, "raw_model", None)
            if not make or not raw_model:
                _LOGGER.error(
                    "%s: refusing unsafe Braiins power-limit write: "
                    "make=%r raw_model=%r coordinator_make=%r "
                    "coordinator_model=%r requested_power_limit=%r",
                    self.coordinator.config_entry.title,
                    make,
                    raw_model,
                    self.coordinator.data.get("make"),
                    self.coordinator.data.get("model"),
                    value,
                )
                raise pyasic.APIError(
                    "Braiins miner model detection is incomplete; refusing to "
                    "overwrite bosminer.toml."
                )

        result = await miner.set_power_limit(int(value))

        if not result:
            raise pyasic.APIError("Failed to set wattage.")

        self._attr_native_value = value
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data["miner_sensors"]["power_limit"] is not None:
            self._attr_native_value = self.coordinator.data["miner_sensors"][
                "power_limit"
            ]

        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available
