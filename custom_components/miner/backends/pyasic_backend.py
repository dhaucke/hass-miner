"""Generic pyasic compatibility backend.

This adapter deliberately owns a single pyasic miner instance. The Home
Assistant coordinator should reuse the backend rather than rediscovering a new
miner object on every refresh.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BackendKind
from .base import BackendUnsupportedError
from .base import FanData
from .base import HashboardData
from .base import MinerCapabilities
from .base import MinerSnapshot
from .base import PowerLimitRange
from .base import UnsafeConfigurationError

if TYPE_CHECKING:
    import pyasic


def _enum_or_value(value: object | None) -> str | None:
    """Return a human readable value for enum-like pyasic fields."""
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


class PyasicBackend:
    """Compatibility adapter for miners supported by pyasic."""

    kind = BackendKind.PYASIC

    def __init__(
        self,
        miner: "pyasic.AnyMiner",
        *,
        minimum_power: int = 15,
        maximum_power: int = 10000,
        power_step: int = 100,
    ) -> None:
        """Initialize a backend around one discovered miner object."""
        self.miner = miner
        self._power_range = PowerLimitRange(
            minimum=minimum_power,
            maximum=maximum_power,
            step=power_step,
        )
        self._last_snapshot: MinerSnapshot | None = None

    @property
    def _unsafe_bosminer_config_writes(self) -> bool:
        """Return whether pyasic would rewrite legacy BOSMiner TOML directly."""
        return type(self.miner).__name__ == "BOSMiner"

    @property
    def capabilities(self) -> MinerCapabilities:
        """Return features reported by pyasic for the connected miner."""
        supports_power = bool(getattr(self.miner, "supports_autotuning", False))
        supports_modes = bool(getattr(self.miner, "supports_power_modes", False))

        # Generic legacy BOSMiner devices remain monitor/control-compatible for
        # non-config operations, but configuration writes are deliberately
        # disabled. A dedicated validated backend must opt in to those writes.
        if self._unsafe_bosminer_config_writes:
            supports_power = False
            supports_modes = False

        return MinerCapabilities(
            power_limit=supports_power,
            pause_resume=bool(getattr(self.miner, "supports_shutdown", False)),
            reboot=hasattr(self.miner, "reboot"),
            restart_backend=hasattr(self.miner, "restart_backend"),
            power_modes=supports_modes,
            fans=bool(getattr(self.miner, "expected_fans", 0)),
            hashboards=bool(getattr(self.miner, "expected_hashboards", 0)),
            diagnostics=True,
            power_limit_range=self._power_range if supports_power else None,
        )

    async def async_refresh(self) -> MinerSnapshot:
        """Read and normalize miner telemetry."""
        import pyasic

        options = [
            pyasic.DataOptions.HOSTNAME,
            pyasic.DataOptions.MAC,
            pyasic.DataOptions.IS_MINING,
            pyasic.DataOptions.FW_VERSION,
            pyasic.DataOptions.HASHRATE,
            pyasic.DataOptions.EXPECTED_HASHRATE,
            pyasic.DataOptions.HASHBOARDS,
            pyasic.DataOptions.WATTAGE,
            pyasic.DataOptions.WATTAGE_LIMIT,
            pyasic.DataOptions.FANS,
            pyasic.DataOptions.CONFIG,
        ]

        try:
            data = await self.miner.get_data(include=options)
        except Exception as err:
            # Preserve the existing VNish compatibility behavior while keeping
            # it isolated inside the pyasic backend.
            if "config" not in str(err).lower():
                raise
            options.remove(pyasic.DataOptions.CONFIG)
            data = await self.miner.get_data(include=options)

        active_preset = None
        try:
            active_preset = data.config.mining_mode.active_preset.name
        except AttributeError:
            pass

        hashboards = tuple(
            HashboardData(
                slot=int(board.slot),
                temperature=board.temp,
                chip_temperature=board.chip_temp,
                hashrate=float(board.hashrate) if board.hashrate is not None else None,
            )
            for board in (data.hashboards or [])
        )
        fans = tuple(
            FanData(index=index, speed=fan.speed)
            for index, fan in enumerate(data.fans or [])
        )

        snapshot = MinerSnapshot(
            host=str(self.miner.ip),
            backend=self.kind,
            manufacturer=_enum_or_value(data.make),
            model=_enum_or_value(data.model),
            firmware=_enum_or_value(data.fw_ver),
            hostname=data.hostname,
            mac=data.mac,
            is_mining=data.is_mining,
            hashrate=float(data.hashrate) if data.hashrate is not None else None,
            ideal_hashrate=(
                float(data.expected_hashrate)
                if data.expected_hashrate is not None
                else None
            ),
            temperature=data.temperature_avg,
            power_limit=data.wattage_limit,
            consumption=data.wattage,
            efficiency=data.efficiency_fract,
            active_preset_name=active_preset,
            hashboards=hashboards,
            fans=fans,
            raw_config=data.config,
        )
        self._last_snapshot = snapshot
        return snapshot

    async def async_set_power_limit(self, value: int) -> None:
        """Set power limit through pyasic for generic compatible miners."""
        if self._unsafe_bosminer_config_writes:
            raise UnsafeConfigurationError(
                "Legacy BOSMiner configuration writes are disabled in the generic "
                "pyasic backend; a validated dedicated backend is required"
            )
        if not self.capabilities.power_limit:
            raise BackendUnsupportedError("Power-limit control is not supported")
        self._power_range.validate(value)

        result = await self.miner.set_power_limit(value)
        if not result:
            raise RuntimeError("pyasic failed to set the requested power limit")

    async def async_pause(self) -> None:
        """Pause mining."""
        if not self.capabilities.pause_resume:
            raise BackendUnsupportedError("Pause/resume is not supported")
        result = await self.miner.stop_mining()
        if result is False:
            raise RuntimeError("Miner did not acknowledge pause request")

    async def async_resume(self) -> None:
        """Resume mining."""
        if not self.capabilities.pause_resume:
            raise BackendUnsupportedError("Pause/resume is not supported")
        result = await self.miner.resume_mining()
        if result is False:
            raise RuntimeError("Miner did not acknowledge resume request")

    async def async_reboot(self) -> None:
        """Reboot miner."""
        if not self.capabilities.reboot:
            raise BackendUnsupportedError("Reboot is not supported")
        result = await self.miner.reboot()
        if result is False:
            raise RuntimeError("Miner did not acknowledge reboot request")

    async def async_restart_backend(self) -> None:
        """Restart firmware mining backend."""
        if not self.capabilities.restart_backend:
            raise BackendUnsupportedError("Backend restart is not supported")
        result = await self.miner.restart_backend()
        if result is False:
            raise RuntimeError("Miner did not acknowledge backend restart request")

    async def async_set_power_mode(self, mode: str) -> None:
        """Set pyasic power mode through the compatibility layer."""
        if self._unsafe_bosminer_config_writes:
            raise UnsafeConfigurationError(
                "Legacy BOSMiner power-mode writes are disabled in the generic backend"
            )
        if not self.capabilities.power_modes:
            raise BackendUnsupportedError("Power modes are not supported")

        from pyasic.config.mining import MiningModeConfig

        modes = {
            "high": MiningModeConfig.high,
            "normal": MiningModeConfig.normal,
            "low": MiningModeConfig.low,
        }
        factory = modes.get(mode)
        if factory is None:
            raise ValueError(f"Unsupported power mode: {mode}")

        config = await self.miner.get_config()
        config.mining_mode = factory()
        await self.miner.send_config(config)

    async def async_diagnostics(self) -> dict[str, object]:
        """Return sanitized generic diagnostics without credentials or pools."""
        snapshot = self._last_snapshot or await self.async_refresh()
        return {
            "backend": self.kind.value,
            "host": snapshot.host,
            "manufacturer": snapshot.manufacturer,
            "model": snapshot.model,
            "firmware": snapshot.firmware,
            "hostname": snapshot.hostname,
            "is_mining": snapshot.is_mining,
            "capabilities": {
                "power_limit": self.capabilities.power_limit,
                "pause_resume": self.capabilities.pause_resume,
                "reboot": self.capabilities.reboot,
                "restart_backend": self.capabilities.restart_backend,
                "power_modes": self.capabilities.power_modes,
            },
            "safety": {
                "legacy_bosminer_config_writes_blocked": self._unsafe_bosminer_config_writes,
            },
            "topology": {
                "hashboards": len(snapshot.hashboards),
                "fans": len(snapshot.fans),
            },
        }
