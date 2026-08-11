"""Common backend contracts for the Miner integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class BackendKind(StrEnum):
    """Backend implementations known to the integration."""

    PYASIC = "pyasic"
    BRAIINS_LEGACY = "braiins_legacy"
    BRAIINS_MODERN = "braiins_modern"


@dataclass(frozen=True, slots=True)
class PowerLimitRange:
    """Supported power-limit range for a miner."""

    minimum: int
    maximum: int
    step: int = 100

    def validate(self, value: int) -> None:
        """Validate a requested power limit."""
        if value < self.minimum or value > self.maximum:
            raise ValueError(
                f"Power limit {value} W is outside the supported range "
                f"{self.minimum}-{self.maximum} W"
            )
        if (value - self.minimum) % self.step != 0:
            raise ValueError(
                f"Power limit {value} W does not match the {self.step} W step"
            )


@dataclass(frozen=True, slots=True)
class MinerCapabilities:
    """Features exposed by a backend for a specific miner."""

    power_limit: bool = False
    pause_resume: bool = False
    reboot: bool = False
    restart_backend: bool = False
    power_modes: bool = False
    fans: bool = False
    hashboards: bool = False
    diagnostics: bool = False
    power_limit_range: PowerLimitRange | None = None


@dataclass(frozen=True, slots=True)
class HashboardData:
    """Normalized hashboard telemetry."""

    slot: int
    temperature: float | None = None
    chip_temperature: float | None = None
    hashrate: float | None = None


@dataclass(frozen=True, slots=True)
class FanData:
    """Normalized fan telemetry."""

    index: int
    speed: int | None = None


@dataclass(frozen=True, slots=True)
class MinerSnapshot:
    """Normalized miner state consumed by Home Assistant entities."""

    host: str
    backend: BackendKind
    manufacturer: str | None = None
    model: str | None = None
    firmware: str | None = None
    hostname: str | None = None
    mac: str | None = None
    is_mining: bool | None = None
    hashrate: float | None = None
    ideal_hashrate: float | None = None
    temperature: float | None = None
    power_limit: int | None = None
    consumption: float | None = None
    efficiency: float | None = None
    active_preset_name: str | None = None
    hashboards: tuple[HashboardData, ...] = field(default_factory=tuple)
    fans: tuple[FanData, ...] = field(default_factory=tuple)
    raw_config: object | None = None


class BackendError(Exception):
    """Base exception for miner backend failures."""


class BackendConnectionError(BackendError):
    """Raised when a miner cannot be reached."""


class BackendAuthenticationError(BackendError):
    """Raised when credentials are rejected."""


class BackendUnsupportedError(BackendError):
    """Raised when a requested operation is not supported."""


class UnsafeConfigurationError(BackendError):
    """Raised when a write cannot be performed without risking miner config."""


@runtime_checkable
class MinerBackend(Protocol):
    """Firmware-independent interface used by the Home Assistant layer."""

    @property
    def kind(self) -> BackendKind:
        """Return backend implementation kind."""

    @property
    def capabilities(self) -> MinerCapabilities:
        """Return capabilities for the connected miner."""

    async def async_refresh(self) -> MinerSnapshot:
        """Return current normalized miner state."""

    async def async_set_power_limit(self, value: int) -> None:
        """Set miner power target."""

    async def async_pause(self) -> None:
        """Pause mining without cutting external power."""

    async def async_resume(self) -> None:
        """Resume mining."""

    async def async_reboot(self) -> None:
        """Reboot the miner."""

    async def async_restart_backend(self) -> None:
        """Restart the firmware mining backend."""

    async def async_diagnostics(self) -> dict[str, object]:
        """Return sanitized backend diagnostics."""
