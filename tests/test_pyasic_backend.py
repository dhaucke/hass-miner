"""Safety and telemetry tests for the generic pyasic compatibility backend."""

from types import SimpleNamespace

import pytest

from custom_components.miner.backends.base import UnsafeConfigurationError
from custom_components.miner.backends.pyasic_backend import PyasicBackend
from custom_components.miner.backends.pyasic_backend import _efficiency_jth
from custom_components.miner.backends.pyasic_backend import _hashrate_ths


class BOSMiner(SimpleNamespace):
    """Minimal object whose runtime type matches pyasic's legacy BOSMiner."""


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


@pytest.mark.asyncio
async def test_unknown_bosminer_is_read_only_for_config_writes() -> None:
    """Unknown legacy BOSMiner hardware must not use pyasic TOML rewrite paths."""
    miner = BOSMiner(
        supports_autotuning=True,
        supports_shutdown=True,
        supports_power_modes=True,
        expected_fans=4,
        expected_hashboards=3,
    )
    backend = PyasicBackend(miner, minimum_power=400, maximum_power=1400)

    assert backend.capabilities.power_limit is False
    assert backend.capabilities.power_modes is False
    assert backend.capabilities.pause_resume is True

    with pytest.raises(UnsafeConfigurationError):
        await backend.async_set_power_limit(600)

    with pytest.raises(UnsafeConfigurationError):
        await backend.async_set_power_mode("low")


def test_hashrate_is_normalized_to_ths() -> None:
    """Unit-aware pyasic values must be converted before casting to float."""
    raw = FakeHashrate(2_600_674_280_516.7, "H")

    assert _hashrate_ths(raw) == pytest.approx(2.6006742805167)


def test_plain_numeric_hashrate_remains_compatible() -> None:
    """Older/plain numeric values are already treated as TH/s."""
    assert _hashrate_ths(13.5) == 13.5
    assert _hashrate_ths(None) is None


def test_efficiency_uses_normalized_ths() -> None:
    """J/TH must be calculated from watts divided by normalized TH/s."""
    assert _efficiency_jth(813, 2.6006742805167) == pytest.approx(312.61)
    assert _efficiency_jth(0, 0) == 0.0
    assert _efficiency_jth(None, 10) is None
