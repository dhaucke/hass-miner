"""Regression tests for legacy Braiins S9 active-state reporting."""

from types import SimpleNamespace

import pytest

from custom_components.miner.backends.base import BackendKind
from custom_components.miner.backends.base import MinerSnapshot
from custom_components.miner.backends.braiins_legacy import (
    BraiinsLegacyS9Backend as BaseBraiinsLegacyS9Backend,
)
from custom_components.miner.backends.braiins_legacy_state import BraiinsLegacyS9Backend


class FakeSSH:
    """Return a deterministic BOSMiner process state."""

    def __init__(self, *, running: bool) -> None:
        self.running = running
        self.commands: list[str] = []

    async def send_command(self, command: str) -> str:
        self.commands.append(command)
        if "pidof bosminer" not in command:
            raise AssertionError(f"Unexpected command: {command}")
        if self.running:
            return "__HASS_MINER_BOS_RUNNING__\n"
        return "__HASS_MINER_BOS_STOPPED__\n"


def _backend(*, running: bool) -> BraiinsLegacyS9Backend:
    miner = SimpleNamespace(ssh=FakeSSH(running=running))
    return BraiinsLegacyS9Backend(miner)


@pytest.mark.asyncio
async def test_refresh_reports_stopped_process_when_pyasic_state_is_stale_true(
    monkeypatch,
) -> None:
    """A stopped BOSMiner process must override stale pyasic is_mining=True."""

    async def fake_parent_refresh(self) -> MinerSnapshot:
        return MinerSnapshot(
            host="192.0.2.10",
            backend=BackendKind.BRAIINS_LEGACY,
            is_mining=True,
        )

    monkeypatch.setattr(
        BaseBraiinsLegacyS9Backend,
        "async_refresh",
        fake_parent_refresh,
    )
    backend = _backend(running=False)

    snapshot = await backend.async_refresh()

    assert snapshot.is_mining is False
    assert backend._last_snapshot is snapshot
    assert any("pidof bosminer" in command for command in backend.miner.ssh.commands)


@pytest.mark.asyncio
async def test_refresh_reports_running_process_when_pyasic_state_is_stale_false(
    monkeypatch,
) -> None:
    """A running BOSMiner process must override stale pyasic is_mining=False."""

    async def fake_parent_refresh(self) -> MinerSnapshot:
        return MinerSnapshot(
            host="192.0.2.11",
            backend=BackendKind.BRAIINS_LEGACY,
            is_mining=False,
        )

    monkeypatch.setattr(
        BaseBraiinsLegacyS9Backend,
        "async_refresh",
        fake_parent_refresh,
    )
    backend = _backend(running=True)

    snapshot = await backend.async_refresh()

    assert snapshot.is_mining is True
    assert backend._last_snapshot is snapshot


@pytest.mark.asyncio
async def test_process_state_requires_unambiguous_marker() -> None:
    """Ambiguous SSH output must not silently invent an Active state."""

    class AmbiguousSSH:
        async def send_command(self, command: str) -> str:
            assert "pidof bosminer" in command
            return ""

    backend = BraiinsLegacyS9Backend(SimpleNamespace(ssh=AmbiguousSSH()))

    with pytest.raises(RuntimeError, match="Unable to determine BOSMiner process state"):
        await backend._async_bosminer_is_running()
