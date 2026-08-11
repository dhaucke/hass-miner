"""Support for Miner sensors."""
from __future__ import annotations

from homeassistant.components.sensor import EntityCategory
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import REVOLUTIONS_PER_MINUTE
from homeassistant.const import UnitOfPower
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .const import JOULES_PER_TERA_HASH
from .const import TERA_HASH_PER_SECOND
from .coordinator import MinerCoordinator
from .entity import MinerEntity


ENTITY_DESCRIPTION_KEY_MAP: dict[str, SensorEntityDescription] = {
    "temperature": SensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_temperature": SensorEntityDescription(
        key="board_temperature",
        translation_key="board_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_temperature": SensorEntityDescription(
        key="chip_temperature",
        translation_key="chip_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "hashrate": SensorEntityDescription(
        key="hashrate",
        translation_key="hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "ideal_hashrate": SensorEntityDescription(
        key="ideal_hashrate",
        translation_key="ideal_hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "active_preset_name": SensorEntityDescription(
        key="active_preset_name",
        translation_key="active_preset_name",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_hashrate": SensorEntityDescription(
        key="board_hashrate",
        translation_key="board_hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "power_limit": SensorEntityDescription(
        key="power_limit",
        translation_key="power_limit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "miner_consumption": SensorEntityDescription(
        key="miner_consumption",
        translation_key="miner_consumption",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "efficiency": SensorEntityDescription(
        key="efficiency",
        translation_key="efficiency",
        native_unit_of_measurement=JOULES_PER_TERA_HASH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "fan_speed": SensorEntityDescription(
        key="fan_speed",
        translation_key="fan_speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for the config entry."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.async_config_entry_first_refresh()

    sensors: list[SensorEntity] = []
    for sensor in coordinator.data["miner_sensors"]:
        description = ENTITY_DESCRIPTION_KEY_MAP.get(sensor)
        if description is None:
            continue
        sensors.append(
            MinerSensor(
                coordinator=coordinator,
                sensor=sensor,
                entity_description=description,
            )
        )

    # Create topology entities only from data actually reported by the backend.
    for board_num in coordinator.data["board_sensors"]:
        for sensor in ("board_temperature", "chip_temperature", "board_hashrate"):
            sensors.append(
                MinerBoardSensor(
                    coordinator=coordinator,
                    board_num=board_num,
                    sensor=sensor,
                    entity_description=ENTITY_DESCRIPTION_KEY_MAP[sensor],
                )
            )

    for fan_num in coordinator.data["fan_sensors"]:
        sensors.append(
            MinerFanSensor(
                coordinator=coordinator,
                fan_num=fan_num,
                sensor="fan_speed",
                entity_description=ENTITY_DESCRIPTION_KEY_MAP["fan_speed"],
            )
        )

    async_add_entities(sensors)


class MinerSensor(MinerEntity, SensorEntity):
    """Defines a miner-level sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        sensor: str,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        identity = self.coordinator.data.get("mac") or self.coordinator.data.get("ip")
        self._attr_unique_id = f"{identity}-{sensor}" if identity else None
        self._sensor = sensor
        self.entity_description = entity_description

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.coordinator.data["miner_sensors"].get(self._sensor)


class MinerBoardSensor(MinerEntity, SensorEntity):
    """Defines a hashboard sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        board_num: int,
        sensor: str,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        identity = self.coordinator.data.get("mac") or self.coordinator.data.get("ip")
        self._attr_unique_id = f"{identity}-{board_num}-{sensor}" if identity else None
        self._attr_translation_placeholders = {"board": str(board_num)}
        self._board_num = board_num
        self._sensor = sensor
        self.entity_description = entity_description

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.coordinator.data["board_sensors"].get(self._board_num, {}).get(
            self._sensor
        )


class MinerFanSensor(MinerEntity, SensorEntity):
    """Defines a fan sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        fan_num: int,
        sensor: str,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        identity = self.coordinator.data.get("mac") or self.coordinator.data.get("ip")
        self._attr_unique_id = f"{identity}-{fan_num}-{sensor}" if identity else None
        self._attr_translation_placeholders = {"fan": str(fan_num)}
        self._fan_num = fan_num
        self._sensor = sensor
        self.entity_description = entity_description

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.coordinator.data["fan_sensors"].get(self._fan_num, {}).get(
            self._sensor
        )
