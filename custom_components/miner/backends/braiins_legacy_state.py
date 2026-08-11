"""Authoritative BOSMiner service-state overlay for legacy Braiins S9 devices."""
from __future__ import annotations

from dataclasses import replace

from .braiins_legacy import BraiinsLegacyS9Backend as _BraiinsLegacyS9Backend

_BOSMINER_RUNNING_MARKER = "__HASS_MINER_BOS_RUNNING__"
_BOSMINER_STOPPED_MARKER = "__HASS_MINER_BOS_STOPPED__"


class BraiinsLegacyS9Backend(_BraiinsLegacyS9Backend):
    """Legacy S9 backend with process-backed active-state reporting."""

    async def _async_bosminer_is_running(self) -> bool:
        """Return the actual BOSMiner process state over SSH."""
        ssh = getattr(self.miner, "ssh", None)
        if ssh is None:
            raise RuntimeError("SSH is required for BOSMiner process-state detection")

        command = (
            "if pidof bosminer >/dev/null 2>&1; then "
            f"echo {_BOSMINER_RUNNING_MARKER}; "
            f"else echo {_BOSMINER_STOPPED_MARKER}; fi"
        )
        result = await ssh.send_command(command)
        if _BOSMINER_RUNNING_MARKER in result:
            return True
        if _BOSMINER_STOPPED_MARKER in result:
            return False
        raise RuntimeError("Unable to determine BOSMiner process state over SSH")

    async def async_refresh(self):
        """Refresh telemetry and replace stale pyasic mining state with process state."""
        snapshot = await super().async_refresh()
        bosminer_running = await self._async_bosminer_is_running()

        # On legacy Braiins OS the Home Assistant Active switch controls the
        # BOSMiner service itself. pyasic's is_mining value can remain stale
        # after that service has exited, so the process state is authoritative.
        snapshot = replace(snapshot, is_mining=bosminer_running)
        self._last_snapshot = snapshot
        return snapshot
