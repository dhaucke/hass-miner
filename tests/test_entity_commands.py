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


def _bosminer_switch_entity(ssh) -> SimpleNamespace:
    """Return a minimal switch stub for direct BOSMiner service control."""
    backend = SimpleNamespace(miner=SimpleNamespace(ssh=ssh))
    coordinator = FakeCoordinator(backend)
    entity = SimpleNamespace(
        coordinator=coordinator,
        _attr_is_on=None,
        async_write_ha_state=lambda: None,
    )
    entity._async_bosminer_is_running = lambda ssh_arg: (  # noqa: E731
        MinerActiveSwitch._async_bosminer_is_running(entity, ssh_arg)
    )
    return entity


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
async def test_bosminer_stop_waits_for_delayed_process_exit(monkeypatch) -> None:
    """A slow legacy init-script stop must not fail on the first process check."""

    class DelayedStopSSH:
        def __init__(self) -> None:
            self.running = True
            self.pending_checks = 0
            self.commands: list[str] = []

        async def send_command(self, command: str) -> str:
            self.commands.append(command)
            if command == "/etc/init.d/bosminer stop":
                self.pending_checks = 2
                return ""
            if "pidof bosminer" in command:
                if self.pending_checks:
                    self.pending_checks -= 1
                    if self.pending_checks == 0:
                        self.running = False
                marker = (
                    "__HASS_MINER_BOS_RUNNING__"
                    if self.running
                    else "__HASS_MINER_BOS_STOPPED__"
                )
                return marker
            raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(
        "custom_components.miner.switch.BOSMINER_STATE_POLL_INTERVAL_SECONDS",
        0,
    )
    ssh = DelayedStopSSH()
    entity = _bosminer_switch_entity(ssh)

    await MinerActiveSwitch._async_set_bosminer_service(entity, False)

    assert entity._attr_is_on is False
    assert "/etc/init.d/bosminer stop" in ssh.commands
    assert sum("pidof bosminer" in command for command in ssh.commands) >= 3


@pytest.mark.asyncio
async def test_bosminer_stop_is_idempotent_when_already_stopped() -> None:
    """Stopping an already stopped BOSMiner must be treated as success."""

    class StoppedSSH:
        def __init__(self) -> None:
            self.commands: list[str] = []

        async def send_command(self, command: str) -> str:
            self.commands.append(command)
            if "pidof bosminer" in command:
                return "__HASS_MINER_BOS_STOPPED__"
            raise AssertionError(f"Unexpected command: {command}")

    ssh = StoppedSSH()
    entity = _bosminer_switch_entity(ssh)

    await MinerActiveSwitch._async_set_bosminer_service(entity, False)

    assert entity._attr_is_on is False
    assert ssh.commands == [ssh.commands[0]]
    assert "/etc/init.d/bosminer stop" not in ssh.commands


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
