"""Regression tests for the legacy Braiins S9 backend."""

from types import SimpleNamespace

import pytest

from custom_components.miner.backends.base import UnsafeConfigurationError
from custom_components.miner.backends.braiins_legacy import BACKUP_PATH
from custom_components.miner.backends.braiins_legacy import BraiinsLegacyS9Backend
from custom_components.miner.backends.braiins_legacy import update_power_target

VALID_CONFIG = """[format]
version = \"2.0\"
generator = \"pyasic\"
model = \"Antminer S9\"
timestamp = 1786375662

[temp_control]
mode = \"manual\"
hot_temp = 90

[fan_control]
min_fans = 1
speed = 100

[autotuning]
enabled = true
mode = \"power_target\"
power_target = 1000

[[group]]
name = \"Default\"
pool = [{url = \"stratum+tcp://example.invalid:3333\", user = \"worker\", password = \"\"}]
quota = 1
"""


def test_update_power_target_changes_only_target() -> None:
    """Changing power must preserve unrelated configuration text."""
    updated = update_power_target(VALID_CONFIG, 600)

    assert "power_target = 600" in updated
    assert 'model = "Antminer S9"' in updated
    assert 'user = "worker"' in updated
    assert updated.replace("power_target = 600", "power_target = 1000") == VALID_CONFIG


@pytest.mark.parametrize("value", [399, 1100, 450])
def test_update_power_target_rejects_unsafe_range(value: int) -> None:
    """S9-specific range and step must be enforced before a write."""
    with pytest.raises(ValueError):
        update_power_target(VALID_CONFIG, value)


def test_update_power_target_rejects_blank_model() -> None:
    """Regression test for the pyasic model corruption incident."""
    corrupt = VALID_CONFIG.replace('model = "Antminer S9"', 'model = " "')

    with pytest.raises(UnsafeConfigurationError):
        update_power_target(corrupt, 600)


def test_update_power_target_rejects_other_model() -> None:
    """S9 write logic must never be applied to another Antminer model."""
    other = VALID_CONFIG.replace('model = "Antminer S9"', 'model = "Antminer S19"')

    with pytest.raises(UnsafeConfigurationError):
        update_power_target(other, 600)


def test_update_power_target_rejects_schema_change() -> None:
    """The backend must not invent a power_target schema it did not find."""
    missing = VALID_CONFIG.replace("power_target = 1000\n", "")

    with pytest.raises(UnsafeConfigurationError):
        update_power_target(missing, 600)


class FakeSSH:
    """Minimal in-memory legacy SSH transport for write-path tests."""

    def __init__(self) -> None:
        self.current = VALID_CONFIG
        self.backup = ""
        self.restart_calls = 0

    async def get_config_file(self) -> str:
        return self.current

    async def send_command(self, command: str) -> str:
        if command == f"cp /etc/bosminer.toml {BACKUP_PATH}":
            self.backup = self.current
        elif command == f"cat {BACKUP_PATH}":
            return self.backup
        elif command == f"cp {BACKUP_PATH} /etc/bosminer.toml":
            self.current = self.backup
        elif "hass-miner.tmp" in command and "power_target = 600" in command:
            self.current = update_power_target(self.current, 600)
        return ""

    async def restart_bosminer(self):
        self.restart_calls += 1
        # Simulate the new config failing to restart. Rollback restart succeeds.
        return None if self.restart_calls == 1 else "restarted"


@pytest.mark.asyncio
async def test_power_write_rolls_back_when_restart_fails(monkeypatch) -> None:
    """A failed BOSMiner restart must restore the validated original config."""
    ssh = FakeSSH()
    miner = SimpleNamespace(
        ssh=ssh,
        supports_autotuning=True,
        supports_shutdown=False,
        supports_power_modes=False,
        expected_fans=0,
        expected_hashboards=0,
    )
    backend = BraiinsLegacyS9Backend(miner)
    backend._identity_validated = True

    async def recovered_immediately(*, attempts=12, delay=2.0) -> None:
        return None

    monkeypatch.setattr(backend, "_wait_for_bosminer", recovered_immediately)

    with pytest.raises(RuntimeError):
        await backend.async_set_power_limit(600)

    assert ssh.current == VALID_CONFIG
    assert ssh.backup == VALID_CONFIG
    assert ssh.restart_calls == 2
