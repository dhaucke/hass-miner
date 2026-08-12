"""Regression tests for the generic pyasic backend against S19/S21/S21+/Hydro shapes.

No S19/S21/S21+ or Hydro hardware is owned by this project, so these tests pin
down PyasicBackend's behavior against pyasic's actual attribute names and data
model for that hardware (expected_fans, and the firmware-dependent
``supports_*`` flags) instead of relying on manual device testing.

Two upstream pyasic facts drive these fixtures:

- Stock Antminer firmware (``AntminerModern``/BMMiner) never sets
  ``supports_autotuning``, so factory S19/S21/S21+ units cannot receive
  power-limit writes through pyasic at all; only ``supports_power_modes``
  (low/normal/high presets) is available.
- Antminer Hydro variants report ``expected_fans = 0`` (water-cooled, no air
  fan RPM), while pyasic's alternate-firmware backends (VNish, LuxOS,
  Whatsminer) expose presets through a separate ``supports_presets`` flag
  that ``PyasicBackend`` does not currently read, so preset switching for
  those firmwares is silently unavailable even though pyasic supports it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.miner.backends.base import BackendUnsupportedError
from custom_components.miner.backends.pyasic_backend import PyasicBackend


class FakeHashrateUnit:
    """Minimal unit enum-like type with a TH target."""

    TH = "TH"


class FakeHashrate:
    """Mimic pyasic's unit-aware hashrate object."""

    def __init__(self, rate: float, unit: str = "H") -> None:
        """Store a synthetic rate and its current unit name."""
        self.rate = rate
        self.unit = FakeHashrateUnit()
        self._unit_name = unit

    def into(self, target) -> FakeHashrate:
        """Convert the synthetic rate into TH/s."""
        assert target == FakeHashrateUnit.TH
        if self._unit_name == "H":
            return FakeHashrate(self.rate / 1_000_000_000_000, "TH")
        return FakeHashrate(self.rate, "TH")

    def __float__(self) -> float:
        """Return the numeric rate in the current synthetic unit."""
        return float(self.rate)


def _board(slot: int, hashrate_ths: float, temp: float, chip_temp: float) -> SimpleNamespace:
    """Build a pyasic-shaped HashBoard stand-in."""
    return SimpleNamespace(
        slot=slot,
        hashrate=FakeHashrate(hashrate_ths, "TH"),
        temp=temp,
        chip_temp=chip_temp,
    )


def _fan(speed: int | None) -> SimpleNamespace:
    """Build a pyasic-shaped Fan stand-in."""
    return SimpleNamespace(speed=speed)


class _FakeAntminer(SimpleNamespace):
    """Base fake pyasic miner exposing what PyasicBackend reads and calls."""

    def __init__(self, *, data: SimpleNamespace, power_limit_result: bool = True, **kwargs) -> None:
        """Store synthetic telemetry and record write-path calls."""
        super().__init__(**kwargs)
        self._data = data
        self._power_limit_result = power_limit_result
        self.set_power_limit_calls: list[int] = []

    async def get_data(self, include=None) -> SimpleNamespace:
        """Return the synthetic MinerData payload."""
        return self._data

    async def set_power_limit(self, value: int) -> bool:
        """Record and acknowledge a power-limit write."""
        self.set_power_limit_calls.append(value)
        return self._power_limit_result


class BMMinerS19(_FakeAntminer):
    """Stock Antminer S19 on factory BMMiner/AntminerModern firmware."""


class BMMinerS21PlusHydro(_FakeAntminer):
    """Stock Antminer S21+ Hydro on factory BMMiner/AntminerModern firmware."""


class VNishS19(_FakeAntminer):
    """Antminer S19 reflashed with VNish firmware."""


def _stock_s19_data() -> SimpleNamespace:
    """Build a realistic-shaped factory S19 telemetry payload."""
    return SimpleNamespace(
        make="AntMiner",
        model="S19",
        fw_ver="Antminer-cgminer-1.0.0",
        hostname="antminer",
        mac="AA:BB:CC:DD:EE:FF",
        is_mining=True,
        hashrate=FakeHashrate(96_000_000_000_000, "H"),
        expected_hashrate=FakeHashrate(95_000_000_000_000, "H"),
        hashboards=[
            _board(0, 32.0, 68.0, 82.0),
            _board(1, 32.0, 69.0, 83.0),
            _board(2, 32.0, 67.0, 81.0),
        ],
        wattage=3250,
        wattage_limit=3250,
        fans=[_fan(3800), _fan(3750), _fan(3820), _fan(3790)],
        temperature_avg=68.0,
        config=None,
    )


def _hydro_s21_plus_data() -> SimpleNamespace:
    """Build a realistic-shaped factory S21+ Hydro telemetry payload.

    Hydro units report no air fan RPM (cooled by an external water loop), but
    pyasic still populates an aggregate board ``temp``/``chip_temp`` for them
    through the same generic averaging path used for air-cooled models.
    """
    return SimpleNamespace(
        make="AntMiner",
        model="S21+ Hyd.",
        fw_ver="Antminer-cgminer-1.0.0",
        hostname="antminer-hydro",
        mac="AA:BB:CC:DD:EE:00",
        is_mining=True,
        hashrate=FakeHashrate(430_000_000_000_000, "H"),
        expected_hashrate=FakeHashrate(430_000_000_000_000, "H"),
        hashboards=[
            _board(0, 143.3, 45.0, 58.0),
            _board(1, 143.3, 46.0, 59.0),
            _board(2, 143.3, 44.0, 57.0),
        ],
        wattage=5510,
        wattage_limit=5510,
        fans=[],
        temperature_avg=45.0,
        config=None,
    )


@pytest.mark.asyncio
async def test_stock_antminer_s19_has_power_modes_but_no_power_limit() -> None:
    """Factory BMMiner firmware exposes presets, never fine-grained power limit."""
    miner = BMMinerS19(
        data=_stock_s19_data(),
        supports_shutdown=True,
        supports_power_modes=True,
        expected_fans=4,
        expected_hashboards=3,
        ip="10.0.0.10",
    )
    backend = PyasicBackend(miner, minimum_power=1000, maximum_power=4000)

    assert backend.capabilities.power_limit is False
    assert backend.capabilities.power_modes is True
    assert backend.capabilities.pause_resume is True
    assert backend.capabilities.fans is True
    assert backend.capabilities.hashboards is True

    snapshot = await backend.async_refresh()
    assert snapshot.manufacturer == "AntMiner"
    assert snapshot.model == "S19"
    assert len(snapshot.hashboards) == 3
    assert len(snapshot.fans) == 4
    assert snapshot.hashrate == pytest.approx(96.0)
    assert snapshot.power_limit == 3250
    assert snapshot.efficiency == pytest.approx(3250 / 96.0, rel=1e-3)

    with pytest.raises(BackendUnsupportedError):
        await backend.async_set_power_limit(3000)
    assert miner.set_power_limit_calls == []


@pytest.mark.asyncio
async def test_stock_antminer_s21_plus_hydro_reports_no_fan_capability() -> None:
    """Hydro units have expected_fans=0; fan capability must reflect that."""
    miner = BMMinerS21PlusHydro(
        data=_hydro_s21_plus_data(),
        supports_shutdown=True,
        supports_power_modes=True,
        expected_fans=0,
        expected_hashboards=3,
        ip="10.0.0.11",
    )
    backend = PyasicBackend(miner, minimum_power=2000, maximum_power=6000)

    assert backend.capabilities.fans is False
    assert backend.capabilities.hashboards is True
    assert backend.capabilities.power_limit is False

    snapshot = await backend.async_refresh()
    assert snapshot.fans == ()
    assert len(snapshot.hashboards) == 3
    assert all(board.temperature is not None for board in snapshot.hashboards)
    assert all(board.chip_temperature is not None for board in snapshot.hashboards)


@pytest.mark.asyncio
async def test_vnish_reflashed_s19_gains_power_limit_via_autotuning() -> None:
    """VNish's supports_autotuning flag enables power-limit writes through pyasic."""
    miner = VNishS19(
        data=_stock_s19_data(),
        supports_shutdown=True,
        supports_autotuning=True,
        supports_presets=True,
        expected_fans=4,
        expected_hashboards=3,
        ip="10.0.0.12",
    )
    backend = PyasicBackend(miner, minimum_power=1000, maximum_power=4000)

    assert backend.capabilities.power_limit is True

    await backend.async_set_power_limit(3000)
    assert miner.set_power_limit_calls == [3000]


@pytest.mark.asyncio
async def test_pyasic_backend_does_not_yet_expose_preset_only_firmware_modes() -> None:
    """Known gap: PyasicBackend only checks supports_power_modes, not supports_presets.

    VNish, LuxOS and Whatsminer(BTMiner) expose mining presets through
    pyasic's separate ``supports_presets`` flag rather than
    ``supports_power_modes`` (used by stock Antminer firmware). This test
    documents that preset switching for those firmwares is currently
    invisible in hass-miner even though pyasic itself supports it.
    """
    miner = VNishS19(
        data=_stock_s19_data(),
        supports_shutdown=True,
        supports_autotuning=True,
        supports_presets=True,
        expected_fans=4,
        expected_hashboards=3,
    )
    backend = PyasicBackend(miner, minimum_power=1000, maximum_power=4000)

    assert backend.capabilities.power_modes is False
