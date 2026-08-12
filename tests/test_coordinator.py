"""Coordinator lifecycle regression tests."""

import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

import custom_components.miner.coordinator as coordinator_module
from custom_components.miner.backends.base import BackendKind
from custom_components.miner.backends.base import MinerCapabilities
from custom_components.miner.backends.base import MinerSnapshot
from custom_components.miner.coordinator import MinerCoordinator
from custom_components.miner.coordinator import RECONNECT_AFTER_FAILURES


def _coordinator_stub(*, backend=None):
    """Return a minimal object accepted by the pure failure helper."""
    reset_calls: list[bool] = []
    coordinator = SimpleNamespace(
        backend=backend,
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
    """Repeated generic failures must request a clean runtime rediscovery."""
    coordinator, reset_calls = _coordinator_stub()

    for _ in range(RECONNECT_AFTER_FAILURES):
        MinerCoordinator._record_failure(coordinator)

    assert reset_calls == [True]
    assert coordinator._failure_count == RECONNECT_AFTER_FAILURES


def test_legacy_braiins_backend_is_kept_when_bosminer_stops() -> None:
    """BOSMiner telemetry loss must not discard the SSH recovery transport."""
    backend = SimpleNamespace(kind=BackendKind.BRAIINS_LEGACY)
    coordinator, reset_calls = _coordinator_stub(backend=backend)

    for _ in range(RECONNECT_AFTER_FAILURES + 2):
        MinerCoordinator._record_failure(coordinator)

    assert reset_calls == []
    assert coordinator.backend is backend
    assert coordinator._failure_count == RECONNECT_AFTER_FAILURES + 2


def test_command_failure_forces_immediate_rediscovery_for_generic_backend() -> None:
    """A single failed write on a generic backend must trigger rediscovery.

    Reads keep resetting _failure_count via the normal 10s poll even when
    every write fails (e.g. a generic backend stuck since a one-time S9
    identity-validation failure at startup), so writes cannot rely on the
    same 3-strike threshold used for read failures.
    """
    coordinator, reset_calls = _coordinator_stub()

    MinerCoordinator.record_command_failure(coordinator)

    assert reset_calls == [True]


def test_command_failure_is_ignored_for_validated_braiins_legacy_backend() -> None:
    """A failed write on an already-validated S9 backend must not discard it."""
    backend = SimpleNamespace(kind=BackendKind.BRAIINS_LEGACY)
    coordinator, reset_calls = _coordinator_stub(backend=backend)

    MinerCoordinator.record_command_failure(coordinator)

    assert reset_calls == []
    assert coordinator.backend is backend


@pytest.mark.asyncio
async def test_upgrade_is_skipped_for_already_validated_backend(monkeypatch) -> None:
    """A validated braiins_legacy backend must never be re-probed or swapped."""
    calls: list[bool] = []

    async def fake_create_backend(*args, **kwargs):
        calls.append(True)
        raise AssertionError("must not be called for an already-validated backend")

    monkeypatch.setattr(coordinator_module, "async_create_backend", fake_create_backend)

    backend = SimpleNamespace(kind=BackendKind.BRAIINS_LEGACY)
    fake = SimpleNamespace(
        backend=backend,
        miner=object(),
        _next_upgrade_attempt=None,
        configured_min_power=15,
        configured_max_power=10000,
    )

    await MinerCoordinator._async_maybe_upgrade_backend(fake)

    assert calls == []
    assert fake.backend is backend


@pytest.mark.asyncio
async def test_upgrade_swaps_to_validated_backend_when_available(monkeypatch) -> None:
    """A generic backend must upgrade in place once S9 identity validates."""
    validated = SimpleNamespace(kind=BackendKind.BRAIINS_LEGACY)

    async def fake_create_backend(*args, **kwargs):
        return validated

    monkeypatch.setattr(coordinator_module, "async_create_backend", fake_create_backend)

    generic = SimpleNamespace(kind=BackendKind.PYASIC)
    fake = SimpleNamespace(
        backend=generic,
        miner=object(),
        _next_upgrade_attempt=None,
        configured_min_power=15,
        configured_max_power=10000,
        config_entry=SimpleNamespace(title="Test Miner"),
    )

    await MinerCoordinator._async_maybe_upgrade_backend(fake)

    assert fake.backend is validated


@pytest.mark.asyncio
async def test_upgrade_keeps_generic_backend_when_still_unavailable(monkeypatch) -> None:
    """A failed re-validation attempt must not disturb the working backend."""
    still_generic = SimpleNamespace(kind=BackendKind.PYASIC)

    async def fake_create_backend(*args, **kwargs):
        return still_generic

    monkeypatch.setattr(coordinator_module, "async_create_backend", fake_create_backend)

    original = SimpleNamespace(kind=BackendKind.PYASIC)
    fake = SimpleNamespace(
        backend=original,
        miner=object(),
        _next_upgrade_attempt=None,
        configured_min_power=15,
        configured_max_power=10000,
    )

    await MinerCoordinator._async_maybe_upgrade_backend(fake)

    assert fake.backend is original


@pytest.mark.asyncio
async def test_upgrade_respects_retry_interval(monkeypatch) -> None:
    """Repeated polls must not re-probe identity on every update cycle."""
    calls: list[bool] = []

    async def fake_create_backend(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(kind=BackendKind.PYASIC)

    monkeypatch.setattr(coordinator_module, "async_create_backend", fake_create_backend)

    fake = SimpleNamespace(
        backend=SimpleNamespace(kind=BackendKind.PYASIC),
        miner=object(),
        _next_upgrade_attempt=None,
        configured_min_power=15,
        configured_max_power=10000,
    )

    await MinerCoordinator._async_maybe_upgrade_backend(fake)
    await MinerCoordinator._async_maybe_upgrade_backend(fake)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_backend_kind_is_exposed_as_a_sensor_value() -> None:
    """The active backend must be visible as a user-facing sensor value.

    Regression coverage for a real-world debugging session where a miner
    silently ran on the generic pyasic backend for hours instead of the
    validated SSH-based braiins_legacy backend, and there was no way to see
    that from the Home Assistant UI without downloading logs.
    """
    snapshot = MinerSnapshot(host="10.0.0.5", backend=BackendKind.BRAIINS_LEGACY)

    class FakeBackend:
        kind = BackendKind.BRAIINS_LEGACY
        capabilities = MinerCapabilities()

        async def async_refresh(self):
            return snapshot

    async def _noop_upgrade():
        return None

    fake = SimpleNamespace(
        backend=FakeBackend(),
        _failure_count=0,
        _record_failure=lambda: None,
        _async_maybe_upgrade_backend=_noop_upgrade,
        configured_min_power=15,
        configured_max_power=10000,
    )

    data = await MinerCoordinator._async_update_data(fake)

    assert data["backend"] == "braiins_legacy"
    assert data["miner_sensors"]["backend"] == "braiins_legacy"


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
