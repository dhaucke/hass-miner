"""Safe backend for legacy BraiinsOS/BOSMiner devices.

The first implementation intentionally reuses pyasic for telemetry and SSH
transport, but it does not use pyasic's BOSMiner.send_config() write path.
That write path rebuilds the complete TOML document from transient metadata and
can corrupt ``[format].model``. This backend changes only the existing
``power_target`` value after independently validating the target S9 identity.
"""
from __future__ import annotations

import asyncio
import json
import re
import tomllib
from dataclasses import replace

from .base import BackendKind
from .base import FanData
from .base import HashboardData
from .base import MinerCapabilities
from .base import PowerLimitRange
from .base import UnsafeConfigurationError
from .pyasic_backend import PyasicBackend

S9_BOARD_NAME = "am1-s9"
S9_MODEL = "Antminer S9"
S9_MANUFACTURER = "Bitmain"
S9_POWER_RANGE = PowerLimitRange(minimum=400, maximum=1400, step=1)
S9_TELEMETRY_MISS_LIMIT = 3

BACKUP_PATH = "/etc/bosminer.toml.hass-miner.bak"
TEMP_PATH = "/etc/bosminer.toml.hass-miner.tmp"
ACTIVE_CONFIG_PATH = "/etc/bosminer.toml"

_SECTION_RE = re.compile(r"^\s*\[([^]]+)]\s*(?:#.*)?$")
_POWER_TARGET_RE = re.compile(
    r"^(?P<prefix>\s*power_target\s*=\s*)(?P<value>\d+)(?P<suffix>\s*(?:#.*)?)$"
)


def _validated_s9_config(raw_config: str) -> dict:
    """Parse and validate a writable legacy S9 BOSMiner configuration."""
    try:
        parsed = tomllib.loads(raw_config)
    except tomllib.TOMLDecodeError as err:
        raise UnsafeConfigurationError("Existing bosminer.toml is invalid TOML") from err

    format_section = parsed.get("format")
    if not isinstance(format_section, dict) or format_section.get("model") != S9_MODEL:
        raise UnsafeConfigurationError(
            "Existing bosminer.toml does not identify a validated Antminer S9"
        )

    autotuning = parsed.get("autotuning")
    if not isinstance(autotuning, dict):
        raise UnsafeConfigurationError("Existing config has no [autotuning] section")
    if autotuning.get("enabled") is not True:
        raise UnsafeConfigurationError(
            "Existing autotuning config is not enabled; refusing power-target write"
        )

    mode = autotuning.get("mode")
    if mode is not None and mode != "power_target":
        raise UnsafeConfigurationError(
            "Existing autotuning mode is not power_target; refusing schema change"
        )
    if not isinstance(autotuning.get("power_target"), int):
        raise UnsafeConfigurationError(
            "Existing autotuning config has no integer power_target; refusing schema change"
        )

    return parsed


def update_power_target(raw_config: str, value: int) -> str:
    """Return config with only ``[autotuning].power_target`` changed."""
    S9_POWER_RANGE.validate(value)
    _validated_s9_config(raw_config)

    lines = raw_config.splitlines(keepends=True)
    section: str | None = None
    matches: list[int] = []

    for index, line in enumerate(lines):
        section_match = _SECTION_RE.match(line.rstrip("\r\n"))
        if section_match:
            section = section_match.group(1).strip()
            continue
        if section == "autotuning" and _POWER_TARGET_RE.match(line.rstrip("\r\n")):
            matches.append(index)

    if len(matches) != 1:
        raise UnsafeConfigurationError(
            "Could not locate exactly one [autotuning].power_target assignment"
        )

    index = matches[0]
    newline = (
        "\r\n"
        if lines[index].endswith("\r\n")
        else "\n"
        if lines[index].endswith("\n")
        else ""
    )
    line = lines[index].rstrip("\r\n")
    match = _POWER_TARGET_RE.match(line)
    if match is None:
        raise UnsafeConfigurationError("Could not safely patch power_target")
    lines[index] = f"{match.group('prefix')}{value}{match.group('suffix')}{newline}"
    updated = "".join(lines)

    candidate = _validated_s9_config(updated)
    if candidate["autotuning"].get("power_target") != value:
        raise UnsafeConfigurationError("Candidate power_target validation failed")

    return updated


def _shell_single_quote(value: str) -> str:
    """Return one POSIX shell single-quoted argument without changing its bytes."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _s9_hashboards_from_temps(rpc_temps: object) -> tuple[HashboardData, ...]:
    """Build real S9 hashboard topology from BOSer's legacy ``temps`` response."""
    if not isinstance(rpc_temps, dict):
        return ()
    rows = rpc_temps.get("TEMPS")
    if not isinstance(rows, list):
        return ()

    boards: list[HashboardData] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        raw_slot = row.get("TEMP")
        raw_id = row.get("ID")
        if isinstance(raw_slot, int):
            slot = raw_slot
        elif isinstance(raw_id, int) and raw_id in (6, 7, 8):
            slot = raw_id - 6
        elif isinstance(raw_id, int):
            slot = raw_id
        else:
            continue

        board_temp = row.get("Board")
        chip_temp = row.get("Chip")
        boards.append(
            HashboardData(
                slot=slot,
                temperature=(
                    float(board_temp) if isinstance(board_temp, (int, float)) else None
                ),
                chip_temperature=(
                    float(chip_temp) if isinstance(chip_temp, (int, float)) else None
                ),
            )
        )

    return tuple(sorted(boards, key=lambda board: board.slot))


def _s9_fans_from_rpc(rpc_fans: object) -> tuple[FanData, ...]:
    """Return populated S9 fans from BOSer's legacy ``fans`` response."""
    if not isinstance(rpc_fans, dict):
        return ()
    rows = rpc_fans.get("FANS")
    if not isinstance(rows, list):
        return ()

    fans: list[FanData] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_index = row.get("FAN", row.get("ID"))
        raw_rpm = row.get("RPM")
        if not isinstance(raw_index, int) or not isinstance(raw_rpm, (int, float)):
            continue
        rpm = int(raw_rpm)
        if rpm <= 0:
            continue
        fans.append(FanData(index=raw_index, speed=rpm))

    return tuple(sorted(fans, key=lambda fan: fan.index))


def _merge_hashboards(
    primary: tuple[HashboardData, ...],
    temperatures: tuple[HashboardData, ...],
) -> tuple[HashboardData, ...]:
    """Merge pyasic hashrates with authoritative BOSer board temperatures."""
    primary_by_slot = {board.slot: board for board in primary}
    temperatures_by_slot = {board.slot: board for board in temperatures}
    slots = sorted(primary_by_slot.keys() | temperatures_by_slot.keys())

    merged: list[HashboardData] = []
    for slot in slots:
        current = primary_by_slot.get(slot)
        temp = temperatures_by_slot.get(slot)
        merged.append(
            HashboardData(
                slot=slot,
                temperature=(
                    temp.temperature
                    if temp is not None and temp.temperature is not None
                    else current.temperature if current is not None else None
                ),
                chip_temperature=(
                    temp.chip_temperature
                    if temp is not None and temp.chip_temperature is not None
                    else current.chip_temperature if current is not None else None
                ),
                hashrate=current.hashrate if current is not None else None,
            )
        )
    return tuple(merged)


def _work_solver_board_temperature(raw_work_solvers: str) -> float | None:
    """Extract aggregate board temperature from BOSminer API JSON."""
    try:
        payload = json.loads(raw_work_solvers)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    temperatures = payload.get("temperatures")
    if not isinstance(temperatures, list):
        return None
    for temperature in temperatures:
        if not isinstance(temperature, dict):
            continue
        if temperature.get("location") != "Board":
            continue
        value = temperature.get("degrees_c")
        if isinstance(value, (int, float)):
            return float(value)
    return None


class BraiinsLegacyS9Backend(PyasicBackend):
    """Legacy BraiinsOS+ backend for positively identified Antminer S9 units."""

    kind = BackendKind.BRAIINS_LEGACY

    def __init__(self, miner) -> None:
        """Initialize the S9 backend around the discovered legacy miner object."""
        super().__init__(
            miner,
            minimum_power=S9_POWER_RANGE.minimum,
            maximum_power=S9_POWER_RANGE.maximum,
            power_step=S9_POWER_RANGE.step,
        )
        self._identity_validated = False
        self._board_cache: dict[int, HashboardData] = {}
        self._board_misses: dict[int, int] = {}
        self._fan_cache: dict[int, FanData] = {}
        self._fan_misses: dict[int, int] = {}

    @property
    def capabilities(self) -> MinerCapabilities:
        """Return conservative capabilities for legacy Braiins S9."""
        generic = super().capabilities
        return MinerCapabilities(
            power_limit=self._identity_validated,
            pause_resume=generic.pause_resume,
            reboot=generic.reboot,
            restart_backend=generic.restart_backend,
            power_modes=False,
            fans=self._identity_validated or generic.fans,
            hashboards=self._identity_validated or generic.hashboards,
            diagnostics=True,
            power_limit_range=S9_POWER_RANGE if self._identity_validated else None,
        )

    async def async_validate_identity(self) -> None:
        """Validate S9 identity before enabling S9-specific write controls."""
        ssh = getattr(self.miner, "ssh", None)
        if ssh is None:
            raise UnsafeConfigurationError("SSH is required for legacy Braiins S9 control")

        board_name = (await ssh.send_command("cat /tmp/sysinfo/board_name")).strip()
        raw_model = await ssh.send_command("cat /etc/bosminer_model.json")
        try:
            model_data = json.loads(raw_model)
        except json.JSONDecodeError as err:
            raise UnsafeConfigurationError(
                "Could not parse /etc/bosminer_model.json"
            ) from err

        if board_name != S9_BOARD_NAME or model_data.get("model") != S9_MODEL:
            raise UnsafeConfigurationError(
                "Legacy Braiins device is not positively identified as Antminer S9"
            )

        self._identity_validated = True

    async def _read_s9_hashboards(self) -> tuple[HashboardData, ...]:
        """Read real S9 board/chip temperatures from BOSer's read-only temps RPC."""
        rpc = getattr(self.miner, "rpc", None)
        if rpc is None or not hasattr(rpc, "temps"):
            return ()
        try:
            return _s9_hashboards_from_temps(await rpc.temps())
        except Exception:
            return ()

    async def _read_s9_fans(self) -> tuple[FanData, ...]:
        """Read populated S9 fans from BOSer's read-only fans RPC."""
        rpc = getattr(self.miner, "rpc", None)
        if rpc is None or not hasattr(rpc, "fans"):
            return ()
        try:
            return _s9_fans_from_rpc(await rpc.fans())
        except Exception:
            return ()

    def _stabilize_hashboards(
        self, boards: tuple[HashboardData, ...]
    ) -> tuple[HashboardData, ...]:
        """Keep the last valid board telemetry across short BOSer dropouts."""
        current = {board.slot: board for board in boards}
        slots = sorted(current.keys() | self._board_cache.keys())
        stabilized: list[HashboardData] = []

        for slot in slots:
            board = current.get(slot)
            cached = self._board_cache.get(slot)
            if board is not None and (
                board.temperature is not None
                or board.chip_temperature is not None
                or board.hashrate is not None
            ):
                merged = HashboardData(
                    slot=slot,
                    temperature=(
                        board.temperature
                        if board.temperature is not None
                        else cached.temperature if cached is not None else None
                    ),
                    chip_temperature=(
                        board.chip_temperature
                        if board.chip_temperature is not None
                        else cached.chip_temperature if cached is not None else None
                    ),
                    hashrate=(
                        board.hashrate
                        if board.hashrate is not None
                        else cached.hashrate if cached is not None else None
                    ),
                )
                self._board_cache[slot] = merged
                self._board_misses[slot] = 0
                stabilized.append(merged)
                continue

            misses = self._board_misses.get(slot, 0) + 1
            self._board_misses[slot] = misses
            if cached is not None and misses < S9_TELEMETRY_MISS_LIMIT:
                stabilized.append(cached)
            else:
                stabilized.append(HashboardData(slot=slot))

        return tuple(stabilized)

    def _stabilize_fans(self, fans: tuple[FanData, ...]) -> tuple[FanData, ...]:
        """Keep populated fan RPM across short BOSer dropouts."""
        current = {fan.index: fan for fan in fans if fan.speed is not None and fan.speed > 0}
        indexes = sorted(current.keys() | self._fan_cache.keys())
        stabilized: list[FanData] = []

        for index in indexes:
            fan = current.get(index)
            cached = self._fan_cache.get(index)
            if fan is not None:
                self._fan_cache[index] = fan
                self._fan_misses[index] = 0
                stabilized.append(fan)
                continue

            misses = self._fan_misses.get(index, 0) + 1
            self._fan_misses[index] = misses
            if cached is not None and misses < S9_TELEMETRY_MISS_LIMIT:
                stabilized.append(cached)
            else:
                stabilized.append(FanData(index=index, speed=None))

        return tuple(stabilized)

    async def _read_s9_temperature_fallback(self) -> float | None:
        """Read aggregate board temperature from the local BOSminer CLI fallback."""
        ssh = getattr(self.miner, "ssh", None)
        if ssh is None:
            return None
        try:
            raw = await ssh.send_command("bosminer api work-solvers --stats Full")
        except Exception:
            return None
        return _work_solver_board_temperature(raw)

    async def async_refresh(self):
        """Refresh telemetry and expose independently validated S9 identity."""
        snapshot = await super().async_refresh()
        if not self._identity_validated:
            await self.async_validate_identity()

        boser_hashboards = await self._read_s9_hashboards()
        hashboards = _merge_hashboards(snapshot.hashboards, boser_hashboards)
        hashboards = self._stabilize_hashboards(hashboards)

        boser_fans = await self._read_s9_fans()
        fans = self._stabilize_fans(boser_fans)

        board_temperatures = [
            board.temperature for board in hashboards if board.temperature is not None
        ]
        if board_temperatures:
            temperature = round(sum(board_temperatures) / len(board_temperatures), 2)
        else:
            temperature = snapshot.temperature
            if temperature is None:
                temperature = await self._read_s9_temperature_fallback()

        active_profile = snapshot.active_preset_name
        if (
            snapshot.power_limit is not None
            and (
                active_profile is None
                or not str(active_profile).strip()
                or str(active_profile).strip().lower() in {"unknown", "unbekannt", "none"}
            )
        ):
            active_profile = "Power Target"

        snapshot = replace(
            snapshot,
            manufacturer=S9_MANUFACTURER,
            model=S9_MODEL,
            backend=self.kind,
            temperature=temperature,
            active_preset_name=active_profile,
            hashboards=hashboards,
            fans=fans,
        )
        self._last_snapshot = snapshot
        return snapshot

    async def _restart_bosminer(self) -> None:
        """Reload BOSMiner through the firmware's own init script."""
        marker = "__HASS_MINER_RESTART_OK__"
        result = await self.miner.ssh.send_command(
            f"/etc/init.d/bosminer reload && echo {marker}"
        )
        if marker not in result:
            raise RuntimeError("BOSMiner init-script reload did not complete successfully")

    async def _wait_for_bosminer(self, *, attempts: int = 12, delay: float = 2.0) -> None:
        """Wait until BOSMiner telemetry responds again after a restart."""
        last_error: Exception | None = None
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(delay)
            try:
                await super().async_refresh()
            except Exception as err:
                last_error = err
                continue
            return

        raise RuntimeError("BOSMiner did not recover after restart") from last_error

    async def _validate_backup(self, original: str) -> None:
        """Verify the dedicated backup is byte-for-byte valid before any write."""
        backup = await self.miner.ssh.send_command(f"cat {BACKUP_PATH}")
        if backup != original:
            raise UnsafeConfigurationError("Dedicated BOSMiner backup verification failed")
        _validated_s9_config(backup)

    async def _restore_backup(self, original: str) -> None:
        """Restore, verify and restart the last validated configuration."""
        ssh = self.miner.ssh
        await ssh.send_command(
            f"cp {BACKUP_PATH} {ACTIVE_CONFIG_PATH} && fsync {ACTIVE_CONFIG_PATH}"
        )
        restored = await ssh.get_config_file()
        if restored != original:
            raise UnsafeConfigurationError("BOSMiner rollback verification failed")
        _validated_s9_config(restored)
        await self._restart_bosminer()
        await self._wait_for_bosminer()

    async def async_set_power_limit(self, value: int) -> None:
        """Safely change only power_target with backup, atomic replace and rollback."""
        if not self._identity_validated:
            await self.async_validate_identity()
        S9_POWER_RANGE.validate(value)

        ssh = self.miner.ssh
        raw_config = await ssh.get_config_file()
        updated = update_power_target(raw_config, value)

        await ssh.send_command(
            f"cp {ACTIVE_CONFIG_PATH} {BACKUP_PATH} && fsync {BACKUP_PATH}"
        )
        await self._validate_backup(raw_config)

        payload = _shell_single_quote(updated)
        write_command = (
            f"printf %s {payload} > {TEMP_PATH} && "
            f"fsync {TEMP_PATH} && "
            f"mv -f {TEMP_PATH} {ACTIVE_CONFIG_PATH} && "
            f"fsync {ACTIVE_CONFIG_PATH}"
        )

        try:
            await ssh.send_command(write_command)
            written = await ssh.get_config_file()
            if written != updated:
                raise UnsafeConfigurationError(
                    "Written BOSMiner configuration differs from validated candidate"
                )
            parsed = _validated_s9_config(written)
            if parsed["autotuning"].get("power_target") != value:
                raise UnsafeConfigurationError("Written power_target does not match request")
            await self._restart_bosminer()
            await self._wait_for_bosminer()
        except Exception as write_err:
            try:
                await self._restore_backup(raw_config)
            except Exception as rollback_err:
                raise UnsafeConfigurationError(
                    "Power target update failed and automatic rollback could not be verified"
                ) from rollback_err
            raise write_err
