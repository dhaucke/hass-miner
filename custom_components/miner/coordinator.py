"""Miner DataUpdateCoordinator."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .backends.base import MinerBackend
from .backends.factory import async_create_backend
from .const import CONF_IP
from .const import CONF_MAX_POWER
from .const import CONF_MIN_POWER
from .const import CONF_RPC_PASSWORD
from .const import CONF_SSH_PASSWORD
from .const import CONF_SSH_USERNAME
from .const import CONF_WEB_PASSWORD
from .const import CONF_WEB_USERNAME

if TYPE_CHECKING:
    import pyasic

_LOGGER = logging.getLogger(__name__)

REQUEST_REFRESH_DEFAULT_COOLDOWN = 5
DEFAULT_MIN_POWER = 15
DEFAULT_MAX_POWER = 10000

DEFAULT_DATA = {
    "hostname": None,
    "mac": None,
    "make": None,
    "model": None,
    "ip": None,
    "is_mining": False,
    "fw_ver": None,
    "backend": None,
    "capabilities": {},
    "miner_sensors": {
        "hashrate": 0,
        "ideal_hashrate": 0,
        "active_preset_name": None,
        "temperature": 0,
        "power_limit": 0,
        "miner_consumption": 0,
        "efficiency": 0.0,
    },
    "board_sensors": {},
    "fan_sensors": {},
    "config": None,
}


class MinerCoordinator(DataUpdateCoordinator):
    """Manage miner backend lifecycle and normalized Home Assistant data."""

    miner: "pyasic.AnyMiner | None"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize MinerCoordinator."""
        self.miner = None
        self.backend: MinerBackend | None = None
        self._failure_count = 0
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=10),
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REQUEST_REFRESH_DEFAULT_COOLDOWN,
                immediate=True,
            ),
        )

    @property
    def available(self) -> bool:
        """Return whether the miner has a backend and the last update succeeded."""
        return self.backend is not None and self.last_update_success

    def _option(self, key: str, default):
        """Return an option, falling back to legacy config-entry data."""
        return self.config_entry.options.get(
            key,
            self.config_entry.data.get(key, default),
        )

    @property
    def configured_min_power(self) -> int:
        """Return generic minimum power override."""
        return int(self._option(CONF_MIN_POWER, DEFAULT_MIN_POWER))

    @property
    def configured_max_power(self) -> int:
        """Return generic maximum power override."""
        return int(self._option(CONF_MAX_POWER, DEFAULT_MAX_POWER))

    async def get_miner(self):
        """Return the persistent pyasic miner used for discovery/compatibility."""
        if self.miner is not None:
            return self.miner

        import pyasic

        miner_ip = self.config_entry.data[CONF_IP]
        miner = await pyasic.get_miner(miner_ip)
        if miner is None:
            return None

        if miner.api is not None and miner.api.pwd is not None:
            miner.api.pwd = self.config_entry.data.get(CONF_RPC_PASSWORD, "")

        if miner.web is not None:
            miner.web.username = self.config_entry.data.get(CONF_WEB_USERNAME, "")
            miner.web.pwd = self.config_entry.data.get(CONF_WEB_PASSWORD, "")

        if miner.ssh is not None:
            miner.ssh.username = self.config_entry.data.get(CONF_SSH_USERNAME, "")
            miner.ssh.pwd = self.config_entry.data.get(CONF_SSH_PASSWORD, "")

        self.miner = miner
        self.backend = await async_create_backend(
            miner,
            minimum_power=self.configured_min_power,
            maximum_power=self.configured_max_power,
        )
        _LOGGER.info(
            "%s: selected %s backend for %s",
            self.config_entry.title,
            self.backend.kind.value,
            miner_ip,
        )
        return miner

    def _offline_data(self) -> dict:
        """Return zeroed first-failure data while preserving configured range."""
        return {
            **DEFAULT_DATA,
            "ip": self.config_entry.data.get(CONF_IP),
            "power_limit_range": {
                "min": self.configured_min_power,
                "max": self.configured_max_power,
                "step": 100,
            },
        }

    async def _async_update_data(self):
        """Fetch and normalize miner data through a persistent backend."""
        if self.backend is None:
            miner = await self.get_miner()
            if miner is None:
                self._failure_count += 1
                if self._failure_count == 1:
                    _LOGGER.warning(
                        "%s: miner is offline; returning zeroed data for first failure",
                        self.config_entry.title,
                    )
                    return self._offline_data()
                raise UpdateFailed("Miner offline")

        try:
            snapshot = await self.backend.async_refresh()
        except Exception as err:
            self._failure_count += 1
            if self._failure_count == 1:
                _LOGGER.warning(
                    "%s: error fetching miner data; returning zeroed data for first "
                    "failure: %s",
                    self.config_entry.title,
                    err,
                )
                return self._offline_data()
            _LOGGER.exception("%s: miner update failed", self.config_entry.title)
            raise UpdateFailed from err

        self._failure_count = 0
        capabilities = self.backend.capabilities
        power_range = capabilities.power_limit_range

        return {
            "hostname": snapshot.hostname,
            "mac": snapshot.mac,
            "make": snapshot.manufacturer,
            "model": snapshot.model,
            "ip": snapshot.host,
            "is_mining": snapshot.is_mining,
            "fw_ver": snapshot.firmware,
            "backend": snapshot.backend.value,
            "capabilities": {
                "power_limit": capabilities.power_limit,
                "pause_resume": capabilities.pause_resume,
                "reboot": capabilities.reboot,
                "restart_backend": capabilities.restart_backend,
                "power_modes": capabilities.power_modes,
                "fans": capabilities.fans,
                "hashboards": capabilities.hashboards,
                "diagnostics": capabilities.diagnostics,
            },
            "miner_sensors": {
                "hashrate": snapshot.hashrate,
                "ideal_hashrate": snapshot.ideal_hashrate,
                "active_preset_name": snapshot.active_preset_name,
                "temperature": snapshot.temperature,
                "power_limit": snapshot.power_limit,
                "miner_consumption": snapshot.consumption,
                "efficiency": snapshot.efficiency,
            },
            "board_sensors": {
                board.slot: {
                    "board_temperature": board.temperature,
                    "chip_temperature": board.chip_temperature,
                    "board_hashrate": board.hashrate,
                }
                for board in snapshot.hashboards
            },
            "fan_sensors": {
                fan.index: {"fan_speed": fan.speed} for fan in snapshot.fans
            },
            "config": snapshot.raw_config,
            "power_limit_range": {
                "min": power_range.minimum if power_range else self.configured_min_power,
                "max": power_range.maximum if power_range else self.configured_max_power,
                "step": power_range.step if power_range else 100,
            },
        }
