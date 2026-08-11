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

from .base import BackendKind
from .base import MinerCapabilities
from .base import PowerLimitRange
from .base import UnsafeConfigurationError
from .pyasic_backend import PyasicBackend

S9_BOARD_NAME = "am1-s9"
S9_MODEL = "Antminer S9"
S9_POWER_RANGE = PowerLimitRange(minimum=400, maximum=1000, step=100)

BACKUP_PATH = "/etc/bosminer.toml.hass-miner.bak"
TEMP_PATH = "/etc/bosminer.toml.hass-miner.tmp"

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
    if autotuning.get("mode") != "power_target":
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

    async def async_refresh(self):
        """Refresh telemetry and validate S9 identity before write controls appear."""
        snapshot = await super().async_refresh()
        if not self._identity_validated:
            await self.async_validate_identity()
        return snapshot

    async def _restart_bosminer(self) -> None:
        """Restart BOSMiner through pyasic's established legacy SSH transport."""
        result = await self.miner.ssh.restart_bosminer()
        if not isinstance(result, str):
            raise TypeError("BOSMiner restart did not return the expected string response")

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
        await ssh.send_command(f"cp {BACKUP_PATH} /etc/bosminer.toml")
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
        await ssh.send_command(f"cp /etc/bosminer.toml {BACKUP_PATH}")
        await self._validate_backup(raw_config)

        delimiter = "__HASS_MINER_BOS_CONFIG__"
        if delimiter in updated:
            raise UnsafeConfigurationError("Unexpected heredoc delimiter in config")

        write_command = (
            f"cat > {TEMP_PATH} <<'{delimiter}'\n"
            f"{updated}\n"
            f"{delimiter}\n"
            f"mv -f {TEMP_PATH} /etc/bosminer.toml"
        )

        try:
            await ssh.send_command(write_command)
            written = await ssh.get_config_file()
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
