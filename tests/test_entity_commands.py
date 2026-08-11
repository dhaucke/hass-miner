"""Regression tests for command entities."""

from types import SimpleNamespace

import pytest

from custom_components.miner.button import MinerCommandButton
from custom_components.miner.switch import MinerActiveSwitch


class FakeBackend:
    """Record switch backend operations."""

    def __init__(self) -> None:
        """Initialize call recorder."""
        self.calls: list[str] = []
        self.kind = SimpleNamespace(value="test")

    async def async_resume(self) -> None:
        """Record resume."""
        self.calls.append("resume")

    async def async_pause(self) -> None:
        """Record pause."""
        self.calls.append("pause")


class FakeCoordinator:
    """Minimal command coordinator with refresh recording."""

    def __init__(self, backend=None) -> None:
        """Initialize coordinator state."""
        self.backend = backend
        self.config_entry = SimpleNamespace(title="Test Miner")
        self.refreshes = 0

    async def async_request_refresh(self) -> None:
        """Record one requested state refresh."""
        self.refreshes += 1


def _generic_switch_entity(coordinator: FakeCoordinator) -> SimpleNamespace:
    """Return a minimal switch stub using the generic non-BOSMiner path."""
    return SimpleNamespace(
        coordinator=coordinator,
        _uses_bosminer_service_control=False,
    )


@pytest.mark.asyncio
async def test_active_switch_refreshes_after_resume() -> None:
    """Resume must be followed by a confirmed coordinator refresh."""
    backend = FakeBackend()
    coordinator = FakeCoordinator(backend)
    entity = _generic_switch_entity(coordinator)

    await MinerActiveSwitch.async_turn_on(entity)

    assert backend.calls == ["resume"]
    assert coordinator.refreshes == 1


@pytest.mark.asyncio
async def test_active_switch_refreshes_after_pause() -> None:
    """Pause must be followed by a confirmed coordinator refresh."""
    backend = FakeBackend()
    coordinator = FakeCoordinator(backend)
    entity = _generic_switch_entity(coordinator)

    await MinerActiveSwitch.async_turn_off(entity)

    assert backend.calls == ["pause"]
    assert coordinator.refreshes == 1


@pytest.mark.asyncio
async def test_switch_does_not_refresh_when_command_fails() -> None:
    """A rejected command must not imply a successful state transition."""

    class FailingBackend(FakeBackend):
        async def async_resume(self) -> None:
            raise RuntimeError("rejected")

    coordinator = FakeCoordinator(FailingBackend())
    entity = _generic_switch_entity(coordinator)

    with pytest.raises(RuntimeError, match="rejected"):
        await MinerActiveSwitch.async_turn_on(entity)

    assert coordinator.refreshes == 0


@pytest.mark.asyncio
async def test_button_refreshes_only_after_successful_command() -> None:
    """Maintenance buttons should refresh telemetry after command completion."""
    calls: list[str] = []

    async def command() -> None:
        calls.append("command")

    coordinator = FakeCoordinator()
    entity = SimpleNamespace(_command=command, coordinator=coordinator)

    await MinerCommandButton.async_press(entity)

    assert calls == ["command"]
    assert coordinator.refreshes == 1
