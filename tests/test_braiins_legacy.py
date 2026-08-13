"""Regression tests for the legacy Braiins S9 backend."""

from types import SimpleNamespace

import pytest

from custom_components.miner.backends.base import BackendKind
from custom_components.miner.backends.base import FanData
from custom_components.miner.backends.base import HashboardData
from custom_components.miner.backends.base import MinerSnapshot
from custom_components.miner.backends.base import UnsafeConfigurationError
from custom_components.miner.backends.braiins_legacy import ACTIVE_CONFIG_PATH
from custom_components.miner.backends.braiins_legacy import BACKUP_PATH
from custom_components.miner.backends.braiins_legacy import BraiinsLegacyS9Backend
from custom_components.miner.backends.braiins_legacy import TEMP_PATH
from custom_components.miner.backends.braiins_legacy import _merge_hashboards
from custom_components.miner.backends.braiins_legacy import _s9_fans_from_rpc
from custom_components.miner.backends.braiins_legacy import _s9_hashboards_from_temps
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


@pytest.mark.parametrize("value", [399, 1500])
def test_update_power_target_rejects_unsafe_range(value: int) -> None:
    """S9-specific safe bounds must be enforced before a write."""
    with pytest.raises(ValueError):
        update_power_target(VALID_CONFIG, value)


def test_update_power_target_accepts_arbitrary_watts_in_verified_range() -> None:
    """Allow any integer watt target from 400 through 1400 W."""
    for value in (400, 450, 999, 1200, 1234, 1400):
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


def test_s9_temps_parser_matches_real_22081_response() -> None:
    """Parse the three physical S9 boards observed on Braiins OS+ 22.08.1."""
    boards = _s9_hashboards_from_temps(
        {
            "TEMPS": [
                {"Board": 43.5, "Chip": 54.1875, "ID": 6, "TEMP": 0},
                {"Board": 42.625, "Chip": 54.8125, "ID": 7, "TEMP": 1},
                {"Board": 42.3125, "Chip": 54.6875, "ID": 8, "TEMP": 2},
            ]
        }
    )

    assert [board.slot for board in boards] == [0, 1, 2]
    assert boards[1].temperature == 42.625
    assert boards[1].chip_temperature == 54.8125


def test_s9_fans_parser_ignores_unpopulated_zero_rpm_headers() -> None:
    """Expose only the two populated fans from the real S9 BOSer response."""
    fans = _s9_fans_from_rpc(
        {
            "FANS": [
                {"FAN": 0, "ID": 0, "RPM": 6180, "Speed": 100},
                {"FAN": 1, "ID": 1, "RPM": 6120, "Speed": 100},
                {"FAN": 2, "ID": 2, "RPM": 0, "Speed": 100},
                {"FAN": 3, "ID": 3, "RPM": 0, "Speed": 100},
            ]
        }
    )

    assert fans == (FanData(index=0, speed=6180), FanData(index=1, speed=6120))


def test_merge_hashboards_keeps_pyasic_hashrate_and_boser_temperatures() -> None:
    """A partial pyasic board must receive temperatures from BOSer without losing hashrate."""
    merged = _merge_hashboards(
        (
            HashboardData(slot=0, hashrate=2.68, temperature=44.0),
            HashboardData(slot=1, hashrate=0.06),
            HashboardData(slot=2, hashrate=2.69, temperature=42.0),
        ),
        (
            HashboardData(slot=0, temperature=43.5, chip_temperature=54.1875),
            HashboardData(slot=1, temperature=42.625, chip_temperature=54.8125),
            HashboardData(slot=2, temperature=42.3125, chip_temperature=54.6875),
        ),
    )

    assert merged[1].hashrate == 0.06
    assert merged[1].temperature == 42.625
    assert merged[1].chip_temperature == 54.8125


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
async def test_s9_refresh_merges_boser_telemetry_and_power_target_profile(monkeypatch) -> None:
    """Merge BOSer temperatures/fans and normalize an Unknown active profile."""

    class FakeRPC:
        """Return the verified read-only S9 telemetry shapes."""

        async def temps(self):
            """Return three board/chip temperature rows."""
            return {
                "TEMPS": [
                    {"ID": 6, "TEMP": 0, "Board": 43.5, "Chip": 54.1},
                    {"ID": 7, "TEMP": 1, "Board": 42.6, "Chip": 54.8},
                    {"ID": 8, "TEMP": 2, "Board": 42.3, "Chip": 54.7},
                ]
            }

        async def fans(self):
            """Return two populated and two empty fan headers."""
            return {
                "FANS": [
                    {"FAN": 0, "RPM": 6180},
                    {"FAN": 1, "RPM": 6120},
                    {"FAN": 2, "RPM": 0},
                    {"FAN": 3, "RPM": 0},
                ]
            }

    miner = SimpleNamespace(
        rpc=FakeRPC(),
        supports_autotuning=True,
        supports_shutdown=False,
        supports_power_modes=False,
        expected_fans=2,
        expected_hashboards=3,
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
            active_preset_name="Unknown",
            hashboards=(
                HashboardData(slot=0, hashrate=2.68),
                HashboardData(slot=1, hashrate=0.06),
                HashboardData(slot=2, hashrate=2.69),
            ),
        )

    monkeypatch.setattr(PyasicBackend, "async_refresh", generic_refresh)

    snapshot = await backend.async_refresh()

    assert snapshot.temperature == pytest.approx(42.8)
    assert snapshot.active_preset_name == "Power Target"
    assert snapshot.hashboards[1].temperature == 42.6
    assert snapshot.hashboards[1].hashrate == 0.06
    assert snapshot.fans == (FanData(index=0, speed=6180), FanData(index=1, speed=6120))


def test_s9_stabilizer_keeps_last_good_values_for_short_dropouts() -> None:
    """Transient missing BOSer polls must not immediately blank HA sensors."""
    miner = SimpleNamespace(
        supports_autotuning=True,
        supports_shutdown=False,
        supports_power_modes=False,
        expected_fans=2,
        expected_hashboards=3,
    )
    backend = BraiinsLegacyS9Backend(miner)

    first_boards = backend._stabilize_hashboards(
        (HashboardData(slot=1, temperature=42.6, chip_temperature=54.8),)
    )
    first_fans = backend._stabilize_fans((FanData(index=0, speed=6180),))
    second_boards = backend._stabilize_hashboards((HashboardData(slot=1),))
    second_fans = backend._stabilize_fans(())

    assert first_boards[0].temperature == 42.6
    assert first_fans[0].speed == 6180
    assert second_boards[0].temperature == 42.6
    assert second_fans[0].speed == 6180


def test_s9_stabilizer_expires_values_after_three_missing_polls() -> None:
    """Persistent missing telemetry must eventually become unavailable."""
    miner = SimpleNamespace(
        supports_autotuning=True,
        supports_shutdown=False,
        supports_power_modes=False,
        expected_fans=2,
        expected_hashboards=3,
    )
    backend = BraiinsLegacyS9Backend(miner)
    backend._stabilize_hashboards(
        (HashboardData(slot=1, temperature=42.6, chip_temperature=54.8),)
    )
    backend._stabilize_fans((FanData(index=0, speed=6180),))

    for _ in range(3):
        boards = backend._stabilize_hashboards((HashboardData(slot=1),))
        fans = backend._stabilize_fans(())

    assert boards[0].temperature is None
    assert boards[0].chip_temperature is None
    assert fans[0].speed is None


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


def _pause_resume_backend() -> BraiinsLegacyS9Backend:
    """Build a backend with pause/resume capability enabled, no RPC wired yet."""
    miner = SimpleNamespace(
        supports_autotuning=True,
        supports_shutdown=True,
        supports_power_modes=False,
        expected_fans=0,
        expected_hashboards=0,
    )
    return BraiinsLegacyS9Backend(miner)


@pytest.mark.asyncio
async def test_async_pause_uses_legacy_rpc_not_pyasics_broken_web_api() -> None:
    """Regression: pyasic's stop_mining() silently fails on this device.

    pyasic resolves this legacy device to a web/gRPC handler with no
    endpoint on old firmware. Pausing must go through the same legacy RPC
    channel temps/devs already use successfully.
    """
    calls: list[str] = []

    class FakeRPC:
        async def pause(self):
            calls.append("pause")
            return {"PAUSE": [{"STATUS": "S", "Msg": "Pausing"}]}

    backend = _pause_resume_backend()
    backend.miner.rpc = FakeRPC()

    await backend.async_pause()

    assert calls == ["pause"]


@pytest.mark.asyncio
async def test_async_resume_uses_legacy_rpc_not_pyasics_broken_web_api() -> None:
    """Same regression as async_pause, for the resume direction."""
    calls: list[str] = []

    class FakeRPC:
        async def resume(self):
            calls.append("resume")
            return {"RESUME": [{"STATUS": "S", "Msg": "Resuming"}]}

    backend = _pause_resume_backend()
    backend.miner.rpc = FakeRPC()

    await backend.async_resume()

    assert calls == ["resume"]


@pytest.mark.asyncio
async def test_async_resume_raises_when_legacy_rpc_does_not_acknowledge() -> None:
    """A negative/empty RPC acknowledgement must still surface as an error."""

    class FakeRPC:
        async def resume(self):
            return {"RESUME": []}

    backend = _pause_resume_backend()
    backend.miner.rpc = FakeRPC()

    with pytest.raises(RuntimeError, match="did not acknowledge resume request"):
        await backend.async_resume()


@pytest.mark.asyncio
async def test_async_resume_raises_when_no_rpc_is_available() -> None:
    """No rpc object at all must fail loudly instead of silently no-op'ing."""
    backend = _pause_resume_backend()
    backend.miner.rpc = None

    with pytest.raises(RuntimeError, match="did not acknowledge resume request"):
        await backend.async_resume()
