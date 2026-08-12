"""Support for miner active-state control."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .backends.base import BackendKind
from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity

_LOGGER = logging.getLogger(__name__)

BOSMINER_CONTROL_TIMEOUT_SECONDS = 8.0
BOSMINER_STATE_POLL_INTERVAL_SECONDS = 0.25
_BOSMINER_RUNNING_MARKER = "__HASS_MINER_BOS_RUNNING__"
_BOSMINER_STOPPED_MARKER = "__HASS_MINER_BOS_STOPPED__"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add switch entities for the config entry."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    if coordinator.backend and coordinator.backend.capabilities.pause_resume:
        async_add_entities([MinerActiveSwitch(coordinator=coordinator)])


class MinerActiveSwitch(MinerEntity, SwitchEntity):
    """Control mining or the BOSMiner service through the selected backend."""

    _attr_translation_key = "active"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        """Initialize the active-state switch."""
        super().__init__(coordinator=coordinator)
        identity = self.coordinator.data.get("mac") or self.coordinator.data.get("ip")
        self._attr_unique_id = f"{identity}-active" if identity else None
        self._attr_is_on = self.coordinator.data.get("is_mining")

    @property
    def _uses_bosminer_service_control(self) -> bool:
        """Return whether this switch controls legacy BOSMiner through SSH."""
        backend = self.coordinator.backend
        return backend is not None and backend.kind is BackendKind.BRAIINS_LEGACY

    @property
    def available(self) -> bool:
        """Keep the legacy BOSMiner switch usable when BOS telemetry is stopped."""
        if self._uses_bosminer_service_control:
            return True
        return super().available

    async def _async_bosminer_is_running(self, ssh) -> bool:
        """Return the BOSMiner process state from an unambiguous SSH marker."""
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
        raise HomeAssistantError("Unable to determine BOSMiner process state over SSH")

    async def _async_set_bosminer_service(self, running: bool) -> None:
        """Start or stop BOSMiner through SSH and wait for the requested state."""
        backend = self.coordinator.backend
        if backend is None:
            raise HomeAssistantError("Miner backend is not available")

        miner = getattr(backend, "miner", None)
        ssh = getattr(miner, "ssh", None)
        if ssh is None:
            raise HomeAssistantError("SSH is not available for BOSMiner service control")

        action = "start" if running else "stop"
        requested_state = "running" if running else "stopped"

        try:
            async with asyncio.timeout(BOSMINER_CONTROL_TIMEOUT_SECONDS):
                # Treat an already-reached state as success. This makes the switch
                # idempotent when BOSMiner was changed from its own web interface.
                if await self._async_bosminer_is_running(ssh) != running:
                    await ssh.send_command(f"/etc/init.d/bosminer {action}")

                    # The legacy init script can return before BOSMiner has fully
                    # started or exited. Poll the actual process state instead of
                    # checking it once in the same shell command.
                    while await self._async_bosminer_is_running(ssh) != running:
                        await asyncio.sleep(BOSMINER_STATE_POLL_INTERVAL_SECONDS)
        except TimeoutError as err:
            raise HomeAssistantError(
                f"BOSMiner did not reach the requested {requested_state} state "
                f"within {BOSMINER_CONTROL_TIMEOUT_SECONDS:g}s"
            ) from err
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to set BOSMiner service to {requested_state}: {err}"
            ) from err

        # Do not synchronously refresh here. A stopped BOSMiner has no telemetry,
        # and waiting for it would turn an intentional OFF command into a failed
        # Home Assistant service call. The normal coordinator poll will recover
        # telemetry after the service is started again.
        self._attr_is_on = running
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Resume mining or start legacy BOSMiner and then refresh actual state."""
        backend = self.coordinator.backend
        if backend is None:
            raise HomeAssistantError("Miner backend is not available")

        _LOGGER.debug(
            "%s: activate mining through %s backend",
            self.coordinator.config_entry.title,
            backend.kind.value,
        )
        if self._uses_bosminer_service_control:
            await self._async_set_bosminer_service(True)
            return

        try:
            await backend.async_resume()
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(f"Failed to resume mining: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Pause mining or stop legacy BOSMiner and then refresh actual state."""
        backend = self.coordinator.backend
        if backend is None:
            raise HomeAssistantError("Miner backend is not available")

        _LOGGER.debug(
            "%s: deactivate mining through %s backend",
            self.coordinator.config_entry.title,
            backend.kind.value,
        )
        if self._uses_bosminer_service_control:
            await self._async_set_bosminer_service(False)
            return

        try:
            await backend.async_pause()
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(f"Failed to pause mining: {err}") from err
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update state from confirmed telemetry without disabling SSH recovery."""
        is_mining = self.coordinator.data.get("is_mining")
        if is_mining is not None and self.coordinator.last_update_success:
            self._attr_is_on = is_mining
        elif self._uses_bosminer_service_control and not self.coordinator.last_update_success:
            # On legacy BOSMiner the most common reason for telemetry loss is an
            # intentionally stopped service. Keep the switch available so HA can
            # start it again over SSH.
            self._attr_is_on = False
        super()._handle_coordinator_update()
