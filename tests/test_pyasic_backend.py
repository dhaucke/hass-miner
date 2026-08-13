"""Safety and telemetry tests for the generic pyasic compatibility backend."""

from __future__ import annotations

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


def _legacy_bosminer(**overrides) -> BOSMiner:
    """Build a BOSMiner-typed miner with pause/reboot capabilities, no RPC/SSH."""
    defaults = {
        "supports_autotuning": True,
        "supports_shutdown": True,
        "supports_power_modes": False,
        "expected_fans": 0,
        "expected_hashboards": 0,
        "reboot": lambda: None,
        "restart_backend": lambda: None,
    }
    defaults.update(overrides)
    return BOSMiner(**defaults)


@pytest.mark.asyncio
async def test_async_resume_falls_back_to_legacy_rpc_when_pyasic_call_fails() -> None:
    """Regression: seen live on a real S9 between validated-SSH windows.

    pyasic's resume_mining() resolves this legacy device to a web/gRPC
    handler with no endpoint on old firmware and returns False; the legacy
    cgminer-style RPC (the same channel board/chip temperature reads
    already use) must be tried next instead of surfacing a false failure.
    """
    calls: list[str] = []

    class FakeRPC:
        async def resume(self):
            calls.append("resume")
            return {"RESUME": [{"STATUS": "S"}]}

    async def failing_resume_mining():
        return False

    miner = _legacy_bosminer(resume_mining=failing_resume_mining, rpc=FakeRPC())
    backend = PyasicBackend(miner)

    await backend.async_resume()

    assert calls == ["resume"]


@pytest.mark.asyncio
async def test_async_pause_falls_back_to_legacy_rpc_when_pyasic_call_fails() -> None:
    """Same regression as resume, for pause."""
    calls: list[str] = []

    class FakeRPC:
        async def pause(self):
            calls.append("pause")
            return {"PAUSE": [{"STATUS": "S"}]}

    async def failing_stop_mining():
        return False

    miner = _legacy_bosminer(stop_mining=failing_stop_mining, rpc=FakeRPC())
    backend = PyasicBackend(miner)

    await backend.async_pause()

    assert calls == ["pause"]


@pytest.mark.asyncio
async def test_async_reboot_falls_back_to_ssh_when_pyasic_call_fails() -> None:
    """Same regression class as resume/pause, for reboot."""
    calls: list[str] = []

    class FakeSSH:
        async def send_command(self, command: str) -> str:
            calls.append(command)
            return "ok"

    async def failing_reboot():
        return False

    miner = _legacy_bosminer(reboot=failing_reboot, ssh=FakeSSH())
    backend = PyasicBackend(miner)

    await backend.async_reboot()

    assert calls == ["/sbin/reboot"]


@pytest.mark.asyncio
async def test_async_restart_backend_falls_back_to_ssh_when_pyasic_call_fails() -> None:
    """Same regression class as resume/pause/reboot, for backend restart."""
    calls: list[str] = []

    class FakeSSH:
        async def send_command(self, command: str) -> str:
            calls.append(command)
            return "__HASS_MINER_GENERIC_RESTART_OK__\n"

    async def failing_restart_backend():
        return False

    miner = _legacy_bosminer(restart_backend=failing_restart_backend, ssh=FakeSSH())
    backend = PyasicBackend(miner)

    await backend.async_restart_backend()

    assert len(calls) == 1
    assert "bosminer reload" in calls[0]


@pytest.mark.asyncio
async def test_async_resume_still_raises_when_legacy_fallback_also_fails() -> None:
    """A genuine double failure must still surface as an error, not a no-op."""

    class FakeRPC:
        async def resume(self):
            return {"RESUME": []}

    async def failing_resume_mining():
        return False

    miner = _legacy_bosminer(resume_mining=failing_resume_mining, rpc=FakeRPC())
    backend = PyasicBackend(miner)

    with pytest.raises(RuntimeError, match="did not acknowledge resume request"):
        await backend.async_resume()


@pytest.mark.asyncio
async def test_async_resume_does_not_fall_back_for_non_bosminer_devices() -> None:
    """The legacy RPC fallback must only ever apply to BOSMiner-typed miners."""
    calls: list[str] = []

    class FakeRPC:
        async def resume(self):
            calls.append("resume")
            return {"RESUME": [{"STATUS": "S"}]}

    async def failing_resume_mining():
        return False

    miner = SimpleNamespace(
        supports_shutdown=True,
        resume_mining=failing_resume_mining,
        rpc=FakeRPC(),
    )
    backend = PyasicBackend(miner)

    with pytest.raises(RuntimeError, match="did not acknowledge resume request"):
        await backend.async_resume()

    assert calls == []
