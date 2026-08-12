"""Miner DataUpdateCoordinator."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from .backends.base import BackendKind
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
RECONNECT_AFTER_FAILURES = 3
DISCOVERY_TIMEOUT_SECONDS = 5.0
REFRESH_TIMEOUT_SECONDS = 6.0
UPGRADE_RETRY_INTERVAL = timedelta(minutes=5)


class MinerCoordinator(DataUpdateCoordinator):
    """Manage miner backend lifecycle and normalized Home Assistant data."""

    miner: pyasic.AnyMiner | None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize MinerCoordinator."""
        self.miner = None
        self.backend: MinerBackend | None = None
        self._failure_count = 0
        self._next_upgrade_attempt = None
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

    def _reset_runtime_backend(self) -> None:
        """Discard stale runtime objects so the next update rediscovers the miner."""
        if self.backend is not None or self.miner is not None:
            _LOGGER.info(
                "%s: discarding stale miner backend after %s consecutive failures",
                self.config_entry.title,
                self._failure_count,
            )
        self.backend = None
        self.miner = None

    def _record_failure(self) -> None:
        """Track failures and rediscover generic backends after repeated errors."""
        self._failure_count += 1

        # A validated legacy Braiins S9 deliberately loses BOSMiner telemetry
        # when its service is stopped. Keep that backend and its SSH transport
        # alive so the Home Assistant switch can start BOSMiner again. Generic
        # backends still use the normal rediscovery policy after repeated errors.
        if self.backend is not None and self.backend.kind is BackendKind.BRAIINS_LEGACY:
            return

        if self._failure_count >= RECONNECT_AFTER_FAILURES:
            self._reset_runtime_backend()

    def record_command_failure(self) -> None:
        """Force rediscovery after a failed write on a non-validated backend.

        Telemetry polling can keep succeeding (resetting the read-failure
        counter every update_interval) even while every write command fails,
        for example when S9 identity validation failed once at startup and
        the coordinator has been stuck on the generic pyasic backend ever
        since. A failed write is a strong, immediate signal that rediscovery
        is worth retrying, so it bypasses the read-failure threshold. A
        backend already validated as BRAIINS_LEGACY is left alone, matching
        the same policy _record_failure uses for read failures.
        """
        if self.backend is not None and self.backend.kind is BackendKind.BRAIINS_LEGACY:
            return
        self._reset_runtime_backend()

    async def _async_maybe_upgrade_backend(self) -> None:
        """Periodically retry the validated S9 backend for a generic fallback.

        A backend that fell back to the generic pyasic path (for example
        after a one-time SSH hiccup during startup) would otherwise never
        retry the safer, dedicated braiins_legacy backend as long as both
        telemetry reads and writes happen to keep succeeding through the
        generic path -- there is no failure to react to. Re-run identity
        validation on a slow interval instead, without disturbing the
        currently working backend if the attempt fails again.
        """
        if self.backend is None or self.backend.kind is BackendKind.BRAIINS_LEGACY:
            return

        now = dt_util.utcnow()
        if self._next_upgrade_attempt is not None and now < self._next_upgrade_attempt:
            return
        self._next_upgrade_attempt = now + UPGRADE_RETRY_INTERVAL

        candidate = await async_create_backend(
            self.miner,
            minimum_power=self.configured_min_power,
            maximum_power=self.configured_max_power,
        )
        if candidate.kind is BackendKind.BRAIINS_LEGACY:
            _LOGGER.info(
                "%s: upgraded from %s to validated braiins_legacy backend",
                self.config_entry.title,
                self.backend.kind.value,
            )
            self.backend = candidate

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

        backend = await async_create_backend(
            miner,
            minimum_power=self.configured_min_power,
            maximum_power=self.configured_max_power,
        )
        self.miner = miner
        self.backend = backend
        _LOGGER.info(
            "%s: selected %s backend for %s",
            self.config_entry.title,
            backend.kind.value,
            miner_ip,
        )
        return miner

    async def _async_update_data(self):
        """Fetch and normalize miner data through a persistent backend."""
        try:
            if self.backend is None:
                try:
                    async with asyncio.timeout(DISCOVERY_TIMEOUT_SECONDS):
                        miner = await self.get_miner()
                except TimeoutError as err:
                    raise UpdateFailed(
                        f"Miner discovery timed out after {DISCOVERY_TIMEOUT_SECONDS:g}s"
                    ) from err
                if miner is None or self.backend is None:
                    raise UpdateFailed("Miner offline")

            try:
                async with asyncio.timeout(REFRESH_TIMEOUT_SECONDS):
                    snapshot = await self.backend.async_refresh()
            except TimeoutError as err:
                raise UpdateFailed(
                    f"Miner refresh timed out after {REFRESH_TIMEOUT_SECONDS:g}s"
                ) from err
        except UpdateFailed:
            self._record_failure()
            raise
        except Exception as err:
            self._record_failure()
            _LOGGER.debug(
                "%s: miner update failed (%s/%s): %s",
                self.config_entry.title,
                self._failure_count,
                RECONNECT_AFTER_FAILURES,
                err,
                exc_info=True,
            )
            raise UpdateFailed(f"Miner update failed: {err}") from err

        self._failure_count = 0
        await self._async_maybe_upgrade_backend()
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
                "backend": snapshot.backend.value,
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
                "step": power_range.step if power_range else 1,
            },
        }
