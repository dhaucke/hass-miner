"""Config flow for the Miner integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import TextSelector
from homeassistant.helpers.selector import TextSelectorConfig
from homeassistant.helpers.selector import TextSelectorType

from .const import CONF_IP
from .const import CONF_MAX_POWER
from .const import CONF_MIN_POWER
from .const import CONF_RPC_PASSWORD
from .const import CONF_SSH_PASSWORD
from .const import CONF_SSH_USERNAME
from .const import CONF_TITLE
from .const import CONF_WEB_PASSWORD
from .const import CONF_WEB_USERNAME
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_MIN_POWER = 15
DEFAULT_MAX_POWER = 10000


def _password_selector() -> TextSelector:
    """Return a password selector used by credential fields."""
    return TextSelector(
        TextSelectorConfig(
            type=TextSelectorType.PASSWORD,
            autocomplete="current-password",
        )
    )


def _looks_like_auth_error(err: Exception) -> bool:
    """Return whether an exception likely represents rejected credentials."""
    message = str(err).lower()
    return any(
        token in message
        for token in ("auth", "password", "permission denied", "unauthorized", "401")
    )


async def _async_discover_miner(host: str):
    """Discover one miner without scanning surrounding networks."""
    import pyasic

    return await pyasic.get_miner(host)


class MinerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a user-friendly config flow for Miner."""

    VERSION = 2
    MINOR_VERSION = 0

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, object] = {}
        self._miner = None
        self._suggested_title = "Miner"

    def _abort_if_host_configured(self, host: str) -> None:
        """Prevent duplicate entries for the same configured host."""
        normalized = host.strip().lower()
        for entry in self._async_current_entries():
            configured = str(entry.data.get(CONF_IP, "")).strip().lower()
            if configured == normalized:
                raise config_entries.AbortFlow("already_configured")

    async def async_step_user(self, user_input=None):
        """Ask only for the miner address and detect the device."""
        if user_input is None:
            user_input = {}

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_IP,
                    default=user_input.get(CONF_IP, ""),
                ): str,
            }
        )

        if not user_input:
            return self.async_show_form(step_id="user", data_schema=schema)

        host = str(user_input[CONF_IP]).strip()
        self._abort_if_host_configured(host)

        try:
            miner = await _async_discover_miner(host)
        except Exception as err:
            _LOGGER.debug("Miner discovery failed for %s: %s", host, err)
            return self.async_show_form(
                step_id="user",
                data_schema=schema,
                errors={"base": "cannot_connect"},
            )

        if miner is None:
            return self.async_show_form(
                step_id="user",
                data_schema=schema,
                errors={"base": "cannot_connect"},
            )

        self._miner = miner
        self._data[CONF_IP] = host
        return await self.async_step_login()

    async def async_step_login(self, user_input=None):
        """Request only credentials exposed by the detected miner backend."""
        if user_input is None:
            user_input = {}

        schema_data: dict[vol.Marker, object] = {}

        rpc = getattr(self._miner, "rpc", None)
        if rpc is not None and getattr(rpc, "pwd", None) is not None:
            schema_data[
                vol.Optional(
                    CONF_RPC_PASSWORD,
                    default=user_input.get(CONF_RPC_PASSWORD, ""),
                )
            ] = _password_selector()

        web = getattr(self._miner, "web", None)
        if web is not None:
            schema_data[
                vol.Optional(
                    CONF_WEB_USERNAME,
                    default=user_input.get(
                        CONF_WEB_USERNAME,
                        getattr(web, "username", "") or "",
                    ),
                )
            ] = str
            schema_data[
                vol.Optional(
                    CONF_WEB_PASSWORD,
                    default=user_input.get(CONF_WEB_PASSWORD, ""),
                )
            ] = _password_selector()

        ssh = getattr(self._miner, "ssh", None)
        if ssh is not None:
            schema_data[
                vol.Optional(
                    CONF_SSH_USERNAME,
                    default=user_input.get(
                        CONF_SSH_USERNAME,
                        getattr(ssh, "username", "") or "root",
                    ),
                )
            ] = str
            schema_data[
                vol.Optional(
                    CONF_SSH_PASSWORD,
                    default=user_input.get(CONF_SSH_PASSWORD, ""),
                )
            ] = _password_selector()

        if not schema_data:
            return await self.async_step_finish()

        schema = vol.Schema(schema_data)
        if not user_input:
            return self.async_show_form(
                step_id="login",
                data_schema=schema,
                description_placeholders=self._device_placeholders(),
            )

        self._data.update(user_input)
        self._apply_credentials()

        try:
            await self._validate_credentials()
        except Exception as err:
            _LOGGER.debug("Credential validation failed: %s", err)
            return self.async_show_form(
                step_id="login",
                data_schema=schema,
                errors={"base": "invalid_auth" if _looks_like_auth_error(err) else "cannot_connect"},
                description_placeholders=self._device_placeholders(),
            )

        return await self.async_step_finish()

    def _apply_credentials(self) -> None:
        """Apply entered credentials to the discovered runtime object."""
        api = getattr(self._miner, "api", None)
        if api is not None and getattr(api, "pwd", None) is not None:
            api.pwd = self._data.get(CONF_RPC_PASSWORD, "")

        web = getattr(self._miner, "web", None)
        if web is not None:
            web.username = self._data.get(CONF_WEB_USERNAME, getattr(web, "username", ""))
            web.pwd = self._data.get(CONF_WEB_PASSWORD, "")

        ssh = getattr(self._miner, "ssh", None)
        if ssh is not None:
            ssh.username = self._data.get(CONF_SSH_USERNAME, getattr(ssh, "username", "root"))
            ssh.pwd = self._data.get(CONF_SSH_PASSWORD, "")

    async def _validate_credentials(self) -> None:
        """Validate connectivity and credentials before creating the entry."""
        title = await self._miner.get_hostname()
        if title:
            self._suggested_title = str(title)

        # For miners exposing SSH, validate the SSH credential separately.
        # This matters for backends such as legacy Braiins where telemetry may
        # work without SSH while safe power-limit control requires it.
        ssh = getattr(self._miner, "ssh", None)
        if ssh is not None and self._data.get(CONF_SSH_USERNAME):
            await ssh.send_command("true")

    def _device_placeholders(self) -> dict[str, str]:
        """Return safe detected-device details for flow descriptions."""
        make = getattr(self._miner, "make", None)
        model = getattr(self._miner, "raw_model", None) or getattr(
            self._miner, "model", None
        )
        return {
            "host": str(self._data.get(CONF_IP, "")),
            "make": str(getattr(make, "value", make) or "Unknown"),
            "model": str(getattr(model, "value", model) or "Unknown"),
        }

    async def async_step_finish(self, user_input=None):
        """Allow a friendly name after successful detection and validation."""
        if user_input is None:
            user_input = {}

        if self._suggested_title == "Miner":
            try:
                title = await self._miner.get_hostname()
            except Exception:
                title = None
            if title:
                self._suggested_title = str(title)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TITLE,
                    default=user_input.get(CONF_TITLE, self._suggested_title),
                ): str,
            }
        )
        if not user_input:
            return self.async_show_form(
                step_id="finish",
                data_schema=schema,
                description_placeholders=self._device_placeholders(),
            )

        self._data.update(user_input)
        return self.async_create_entry(
            title=str(self._data[CONF_TITLE]),
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return advanced options flow."""
        return MinerOptionsFlow(config_entry)


class MinerOptionsFlow(config_entries.OptionsFlow):
    """Advanced options kept out of the normal onboarding flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage advanced generic power-range overrides."""
        if user_input is not None:
            minimum = user_input[CONF_MIN_POWER]
            maximum = user_input[CONF_MAX_POWER]
            if minimum >= maximum:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(user_input),
                    errors={"base": "invalid_power_range"},
                )
            return self.async_create_entry(title="", data=user_input)

        values = {
            CONF_MIN_POWER: self.config_entry.options.get(
                CONF_MIN_POWER,
                self.config_entry.data.get(CONF_MIN_POWER, DEFAULT_MIN_POWER),
            ),
            CONF_MAX_POWER: self.config_entry.options.get(
                CONF_MAX_POWER,
                self.config_entry.data.get(CONF_MAX_POWER, DEFAULT_MAX_POWER),
            ),
        }
        return self.async_show_form(step_id="init", data_schema=self._schema(values))

    @staticmethod
    def _schema(values: dict[str, int]) -> vol.Schema:
        """Return advanced options schema."""
        return vol.Schema(
            {
                vol.Required(CONF_MIN_POWER, default=values[CONF_MIN_POWER]): vol.All(
                    vol.Coerce(int), vol.Range(min=15, max=10000)
                ),
                vol.Required(CONF_MAX_POWER, default=values[CONF_MAX_POWER]): vol.All(
                    vol.Coerce(int), vol.Range(min=15, max=10000)
                ),
            }
        )
