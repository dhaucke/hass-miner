"""Coordinator lifecycle regression tests."""

import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

import custom_components.miner.coordinator as coordinator_module
from custom_components.miner.coordinator import MinerCoordinator
from custom_components.miner.coordinator import RECONNECT_AFTER_FAILURES


def _coordinator_stub():
    """Return a minimal object accepted by the pure failure helper."""
    reset_calls: list[bool] = []
    coordinator = SimpleNamespace(
        _failure_count=0,
        _reset_runtime_backend=lambda: reset_calls.append(True),
    )
    return coordinator, reset_calls


def test_backend_is_kept_for_transient_failures() -> None:
    """One or two failed polls should not trigger rediscovery."""
    coordinator, reset_calls = _coordinator_stub()

    for _ in range(RECONNECT_AFTER_FAILURES - 1):
        MinerCoordinator._record_failure(coordinator)

    assert reset_calls == []
    assert coordinator._failure_count == RECONNECT_AFTER_FAILURES - 1


def test_backend_is_rediscovered_after_repeated_failures() -> None:
    """Repeated failures must request a clean runtime rediscovery."""
    coordinator, reset_calls = _coordinator_stub()

    for _ in range(RECONNECT_AFTER_FAILURES):
        MinerCoordinator._record_failure(coordinator)

    assert reset_calls == [True]
    assert coordinator._failure_count == RECONNECT_AFTER_FAILURES


@pytest.mark.asyncio
async def test_discovery_timeout_fails_fast(monkeypatch) -> None:
    """A stalled pyasic discovery must not hold Home Assistant startup indefinitely."""
    failures: list[bool] = []

    async def stalled_discovery():
        await asyncio.sleep(1)
        return None

    fake = SimpleNamespace(
        backend=None,
        _failure_count=0,
        get_miner=stalled_discovery,
        _record_failure=lambda: failures.append(True),
    )
    monkeypatch.setattr(coordinator_module, "DISCOVERY_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(UpdateFailed, match="discovery timed out"):
        await MinerCoordinator._async_update_data(fake)

    assert failures == [True]


@pytest.mark.asyncio
async def test_refresh_timeout_fails_fast(monkeypatch) -> None:
    """A stalled miner backend poll must be cancelled before the next poll interval."""
    failures: list[bool] = []

    class StalledBackend:
        """Backend that never completes within the test timeout."""

        async def async_refresh(self):
            """Simulate a BOS/BOSer request that has stopped responding."""
            await asyncio.sleep(1)
            return None

    fake = SimpleNamespace(
        backend=StalledBackend(),
        _failure_count=0,
        _record_failure=lambda: failures.append(True),
    )
    monkeypatch.setattr(coordinator_module, "REFRESH_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(UpdateFailed, match="refresh timed out"):
        await MinerCoordinator._async_update_data(fake)

    assert failures == [True]
