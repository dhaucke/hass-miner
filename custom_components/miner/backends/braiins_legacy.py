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
from .base import MinerCapabilities
from .base import PowerLimitRange
from .base import UnsafeConfigurationError
from .pyasic_backend import PyasicBackend

S9_BOARD_NAME = "am1-s9"
S9_MODEL = "Antminer S9"
S9_MANUFACTURER = "Bitmain"
S9_POWER_RANGE = PowerLimitRange(minimum=400, maximum=1400, step=100)

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

    # Braiins OS+ 22.08.1 can emit a valid S9 config with power_target but no
    # explicit mode. An explicit mode is still required to be power_target.
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
    if match is None:  # Defensive: the line was matched above.
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


def _average_board_temperature(rpc_temps: object) -> float | None:
    """Return the average S9 board temperature from BOSMiner's legacy temps RPC."""
    if not isinstance(rpc_temps, dict):
        return None
    rows = rpc_temps.get("TEMPS")
    if not isinstance(rows, list):
        return None

    values = [
        float(row["Board"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("Board"), (int, float))
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


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
            fans=generic.fans,
            hashboards=generic.hashboards,
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

    async def _read_s9_temperature(self) -> float | None:
        """Read board temperature without relying on pyasic model detection."""
        rpc = getattr(self.miner, "rpc", None)
        if rpc is not None and hasattr(rpc, "temps"):
            try:
                temperature = _average_board_temperature(await rpc.temps())
            except Exception:
                temperature = None
            if temperature is not None:
                return temperature

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

        temperature = snapshot.temperature
        if temperature is None:
            temperature = await self._read_s9_temperature()

        active_profile = snapshot.active_preset_name
        if active_profile is None and snapshot.power_limit is not None:
            active_profile = "Power Target"

        # pyasic 0.78.8 may report empty make/model for this legacy BOS+ build.
        # Once the two independent firmware identity checks have passed, use
        # that stronger evidence for Home Assistant device metadata. The same
        # build can also omit topology-derived temperature and preset metadata,
        # so fill those from verified read-only BOSMiner telemetry.
        snapshot = replace(
            snapshot,
            manufacturer=S9_MANUFACTURER,
            model=S9_MODEL,
            backend=self.kind,
            temperature=temperature,
            active_preset_name=active_profile,
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
            except Exception as err:  # The daemon may still be starting.
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

        # A dedicated backup is created only from an already validated config,
        # then read back and validated before the active file is touched.
        await ssh.send_command(
            f"cp {ACTIVE_CONFIG_PATH} {BACKUP_PATH} && fsync {BACKUP_PATH}"
        )
        await self._validate_backup(raw_config)

        # printf with a POSIX-safe single-quoted argument preserves the exact
        # candidate text, including its original terminal-newline state.
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
