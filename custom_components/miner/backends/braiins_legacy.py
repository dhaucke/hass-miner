"""Safe backend for legacy BraiinsOS/BOSMiner devices.

The first implementation intentionally reuses pyasic for telemetry and SSH
transport, but it does not use pyasic's BOSMiner.send_config() write path.
That write path rebuilds the complete TOML document from transient metadata and
can corrupt ``[format].model``.  This backend changes only the existing
``power_target`` value after independently validating the target S9 identity.
"""
from __future__ import annotations

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

_POWER_TARGET_RE = re.compile(
    r"(?m)^(?P<prefix>\s*power_target\s*=\s*)(?P<value>\d+)(?P<suffix>\s*(?:#.*)?)$"
)


def update_power_target(raw_config: str, value: int) -> str:
    """Return config with only an existing power_target value changed."""
    S9_POWER_RANGE.validate(value)

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
    if "power_target" not in autotuning:
        raise UnsafeConfigurationError(
            "Existing autotuning config has no power_target; refusing schema change"
        )

    updated, replacements = _POWER_TARGET_RE.subn(
        lambda match: f"{match.group('prefix')}{value}{match.group('suffix')}",
        raw_config,
        count=1,
    )
    if replacements != 1:
        raise UnsafeConfigurationError(
            "Could not locate exactly one power_target assignment in bosminer.toml"
        )

    # Parse the candidate again before it can ever reach the miner.
    try:
        candidate = tomllib.loads(updated)
    except tomllib.TOMLDecodeError as err:
        raise UnsafeConfigurationError("Generated bosminer.toml is invalid") from err
    if candidate.get("format", {}).get("model") != S9_MODEL:
        raise UnsafeConfigurationError("Candidate config lost the validated S9 model")
    if candidate.get("autotuning", {}).get("power_target") != value:
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
        """Validate hardware identity from two independent firmware sources."""
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
                "Legacy Braiins device is not independently identified as Antminer S9"
            )

        self._identity_validated = True

    async def async_refresh(self):
        """Refresh telemetry and validate S9 identity once before write controls appear."""
        snapshot = await super().async_refresh()
        if not self._identity_validated:
            await self.async_validate_identity()
        return snapshot

    async def async_set_power_limit(self, value: int) -> None:
        """Safely change only power_target with backup, atomic replace and rollback."""
        if not self._identity_validated:
            await self.async_validate_identity()
        S9_POWER_RANGE.validate(value)

        ssh = self.miner.ssh
        raw_config = await ssh.get_config_file()
        updated = update_power_target(raw_config, value)

        # Keep a dedicated HA backup only after the current config passed all
        # validation. Never trust or overwrite the firmware's generic .bak file.
        await ssh.send_command(
            "cp /etc/bosminer.toml /etc/bosminer.toml.ha-backup && "
            "fsync /etc/bosminer.toml.ha-backup"
        )

        delimiter = "__HASS_MINER_BOS_CONFIG__"
        if delimiter in updated:
            raise UnsafeConfigurationError("Unexpected heredoc delimiter in config")
        write_command = (
            "cat > /etc/bosminer.toml.ha-tmp <<'"
            + delimiter
            + "'\n"
            + updated
            + "\n"
            + delimiter
            + "\n"
            + "mv /etc/bosminer.toml.ha-tmp /etc/bosminer.toml && "
            + "fsync /etc/bosminer.toml && /etc/init.d/bosminer reload"
        )

        try:
            await ssh.send_command(write_command)
            # Re-read after the atomic replace. This validates what actually
            # reached persistent storage before reporting success to HA.
            written = await ssh.get_config_file()
            parsed = tomllib.loads(written)
            if parsed.get("format", {}).get("model") != S9_MODEL:
                raise UnsafeConfigurationError("Written config has invalid model")
            if parsed.get("autotuning", {}).get("power_target") != value:
                raise UnsafeConfigurationError("Written power_target does not match request")
        except Exception:
            await ssh.send_command(
                "cp /etc/bosminer.toml.ha-backup /etc/bosminer.toml && "
                "fsync /etc/bosminer.toml && /etc/init.d/bosminer reload"
            )
            raise
