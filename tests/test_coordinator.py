"""Coordinator lifecycle regression tests."""

from types import SimpleNamespace

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
