"""Coordinator lifecycle regression tests."""

from types import SimpleNamespace

from custom_components.miner.coordinator import MinerCoordinator
from custom_components.miner.coordinator import RECONNECT_AFTER_FAILURES


def _coordinator_stub() -> MinerCoordinator:
    """Create a minimal coordinator instance for pure lifecycle helpers."""
    coordinator = object.__new__(MinerCoordinator)
    coordinator._failure_count = 0
    coordinator.backend = object()
    coordinator.miner = object()
    coordinator.config_entry = SimpleNamespace(title="Test miner")
    return coordinator


def test_backend_is_kept_for_transient_failures() -> None:
    """One or two failed polls should not immediately discard runtime state."""
    coordinator = _coordinator_stub()

    for _ in range(RECONNECT_AFTER_FAILURES - 1):
        coordinator._record_failure()

    assert coordinator.backend is not None
    assert coordinator.miner is not None
    assert coordinator._failure_count == RECONNECT_AFTER_FAILURES - 1


def test_backend_is_rediscovered_after_repeated_failures() -> None:
    """Repeated failures must clear stale pyasic/backend runtime objects."""
    coordinator = _coordinator_stub()

    for _ in range(RECONNECT_AFTER_FAILURES):
        coordinator._record_failure()

    assert coordinator.backend is None
    assert coordinator.miner is None
    assert coordinator._failure_count == RECONNECT_AFTER_FAILURES
