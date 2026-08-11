"""Regression tests for the legacy Braiins S9 backend."""

from types import SimpleNamespace

import pytest

from custom_components.miner.backends.base import BackendKind
from custom_components.miner.backends.base import MinerSnapshot
from custom_components.miner.backends.base import UnsafeConfigurationError
from custom_components.miner.backends.braiins_legacy import ACTIVE_CONFIG_PATH
from custom_components.miner.backends.braiins_legacy import BACKUP_PATH
from custom_components.miner.backends.braiins_legacy import BraiinsLegacyS9Backend
from custom_components.miner.backends.braiins_legacy import TEMP_PATH
from custom_components.miner.backends.braiins_legacy import _average_board_temperature
from custom_components.miner.backends.braiins_legacy import _work_solver_board_temperature
from custom_components.miner.backends.braiins_legacy import update_power_target
from custom_components.miner.backends.pyasic_backend import PyasicBackend

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

BRAIINS_22081_CONFIG = """[format]
version = '2.0'
model = 'Antminer S9'
generator = 'BOSer (boser-openwrt 0.1.0-26ba61b9)'
timestamp = 1786438416

[[group]]
name = 'Default'

[[group.pool]]
url = 'stratum2+tcp://example.invalid/test-public-key'
user = '!non-existent-user!'

[autotuning]
enabled = true
power_target = 1200
"""


def test_update_power_target_changes_only_target() -> None:
    """Changing power must preserve unrelated configuration text."""
    updated = update_power_target(VALID_CONFIG, 600)

    assert "power_target = 600" in updated
    assert 'model = "Antminer S9"' in updated
    assert 'user = "worker"' in updated
    assert updated.replace("power_target = 600", "power_target = 1000") == VALID_CONFIG


def test_update_power_target_accepts_verified_22081_schema_without_mode() -> None:
    """Braiins 22.08.1 BOSer config may omit mode while retaining power_target."""
    updated = update_power_target(BRAIINS_22081_CONFIG, 1400)

    assert "power_target = 1400" in updated
    assert "mode =" not in updated
    assert "generator = 'BOSer (boser-openwrt 0.1.0-26ba61b9)'" in updated
    assert updated.replace("power_target = 1400", "power_target = 1200") == BRAIINS_22081_CONFIG


@pytest.mark.parametrize("value", [399, 1500, 450])
def test_update_power_target_rejects_unsafe_range(value: int) -> None:
    """S9-specific range and step must be enforced before a write."""
    with pytest.raises(ValueError):
        update_power_target(VALID_CONFIG, value)


def test_update_power_target_accepts_full_verified_range() -> None:
    """Allow 400-1400 W in 100 W steps for the validated S9 backend."""
    for value in range(400, 1401, 100):
        updated = update_power_target(VALID_CONFIG, value)
        assert f"power_target = {value}" in updated


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


def test_update_power_target_rejects_disabled_autotuning() -> None:
    """A disabled autotuner must not be silently converted by a power write."""
    disabled = VALID_CONFIG.replace("enabled = true", "enabled = false")

    with pytest.raises(UnsafeConfigurationError):
        update_power_target(disabled, 600)


def test_update_power_target_rejects_explicit_other_mode() -> None:
    """An explicit non-power-target mode must remain fail-safe."""
    other_mode = VALID_CONFIG.replace('mode = "power_target"', 'mode = "manual"')

    with pytest.raises(UnsafeConfigurationError):
        update_power_target(other_mode, 600)


def test_update_power_target_rejects_schema_change() -> None:
    """The backend must not invent a power_target schema it did not find."""
    missing = VALID_CONFIG.replace("power_target = 1000\n", "")

    with pytest.raises(UnsafeConfigurationError):
        update_power_target(missing, 600)


def test_average_board_temperature_uses_legacy_temps_rpc() -> None:
    """Average real S9 board readings without requiring pyasic model metadata."""
    rpc_temps = {
        "TEMPS": [
            {"ID": 6, "Board": 42.0, "Chip": 53.0},
            {"ID": 7, "Board": 44.5, "Chip": 55.0},
            {"ID": 8, "Board": 43.0, "Chip": 54.0},
        ]
    }

    assert _average_board_temperature(rpc_temps) == 43.17


def test_work_solver_temperature_matches_verified_22081_output() -> None:
    """Parse the aggregate Board temperature observed on Braiins OS+ 22.08.1."""
    raw = """{
      "temperatures": [
        {"location": "Board", "degrees_c": 43.5625},
        {"location": "Chip", "degrees_c": 55.0}
      ]
    }"""

    assert _work_solver_board_temperature(raw) == 43.5625


@pytest.mark.asyncio
async def test_validated_s9_identity_replaces_empty_pyasic_metadata(monkeypatch) -> None:
    """Independent S9 identity checks should drive Home Assistant device metadata."""
    miner = SimpleNamespace(
        supports_autotuning=True,
        supports_shutdown=False,
        supports_power_modes=False,
        expected_fans=0,
        expected_hashboards=0,
    )
    backend = BraiinsLegacyS9Backend(miner)
    backend._identity_validated = True

    async def generic_refresh(_self) -> MinerSnapshot:
        return MinerSnapshot(
            host="192.0.2.10",
            backend=BackendKind.PYASIC,
            manufacturer="",
            model="",
            firmware="22.08.1",
        )

    monkeypatch.setattr(PyasicBackend, "async_refresh", generic_refresh)

    snapshot = await backend.async_refresh()

    assert snapshot.backend is BackendKind.BRAIINS_LEGACY
    assert snapshot.manufacturer == "Bitmain"
    assert snapshot.model == "Antminer S9"
    assert snapshot.firmware == "22.08.1"


@pytest.mark.asyncio
async def test_s9_refresh_fills_temperature_and_power_target_profile(monkeypatch) -> None:
    """Fill missing legacy BOS+ telemetry from the dedicated S9 read path."""

    class FakeRPC:
        async def temps(self):
            return {
                "TEMPS": [
                    {"ID": 6, "Board": 43.0, "Chip": 54.0},
                    {"ID": 7, "Board": 44.0, "Chip": 55.0},
                    {"ID": 8, "Board": 45.0, "Chip": 56.0},
                ]
            }

    miner = SimpleNamespace(
        rpc=FakeRPC(),
        supports_autotuning=True,
        supports_shutdown=False,
        supports_power_modes=False,
        expected_fans=0,
        expected_hashboards=0,
    )
    backend = BraiinsLegacyS9Backend(miner)
    backend._identity_validated = True

    async def generic_refresh(_self) -> MinerSnapshot:
        return MinerSnapshot(
            host="192.0.2.10",
            backend=BackendKind.PYASIC,
            firmware="22.08.1",
            power_limit=1000,
            temperature=None,
            active_preset_name=None,
        )

    monkeypatch.setattr(PyasicBackend, "async_refresh", generic_refresh)

    snapshot = await backend.async_refresh()

    assert snapshot.temperature == 44.0
    assert snapshot.active_preset_name == "Power Target"


class FakeSSH:
    """Minimal in-memory legacy SSH transport for write-path tests."""

    def __init__(self) -> None:
        """Initialize an in-memory config and restart counter."""
        self.current = VALID_CONFIG
        self.backup = ""
        self.restart_calls = 0

    async def get_config_file(self) -> str:
        """Return the simulated active BOSMiner configuration."""
        return self.current

    async def send_command(self, command: str) -> str:
        """Handle the subset of SSH commands used by the write-path test."""
        if command.startswith(f"cp {ACTIVE_CONFIG_PATH} {BACKUP_PATH}"):
            self.backup = self.current
        elif command == f"cat {BACKUP_PATH}":
            return self.backup
        elif command.startswith(f"cp {BACKUP_PATH} {ACTIVE_CONFIG_PATH}"):
            self.current = self.backup
        elif command.startswith("printf %s ") and TEMP_PATH in command:
            self.current = update_power_target(self.current, 600)
        elif command.startswith("/etc/init.d/bosminer reload"):
            self.restart_calls += 1
            if self.restart_calls > 1:
                return "__HASS_MINER_RESTART_OK__\n"
        return ""


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
        """Skip telemetry waiting in the in-memory rollback test."""
        return None

    monkeypatch.setattr(backend, "_wait_for_bosminer", recovered_immediately)

    with pytest.raises(RuntimeError):
        await backend.async_set_power_limit(600)

    assert ssh.current == VALID_CONFIG
    assert ssh.backup == VALID_CONFIG
    assert ssh.restart_calls == 2
