"""Config flow: consumer OAuth PKCE login (paste-back), plus reauth."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import auth
from .api import MieleApiError, MieleCloud
from .const import (
    CONF_ADAPTIVE,
    CONF_COUNTRY,
    CONF_MAC,
    CONF_SCAN_INTERVAL,
    CONF_TOKENS,
    DEFAULT_ADAPTIVE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


class MieleWineConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle initial login + reauthentication."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MieleWineOptionsFlow:
        """Expose the polling options (Configure button on the integration card)."""
        return MieleWineOptionsFlow()

    def __init__(self) -> None:
        self._challenge: dict[str, str] | None = None
        self._tokens: dict[str, Any] | None = None
        self._authorize_url: str = ""
        self._reauth_entry: ConfigEntry | None = None

    # --- initial setup ---------------------------------------------------
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: choose country, generate the authorize URL."""
        if user_input is not None:
            return self._begin_login(user_input[CONF_COUNTRY])
        countries = sorted(auth.CONSUMER_CLIENT_IDS)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COUNTRY, default="be"): SelectSelector(
                        SelectSelectorConfig(
                            options=countries,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=True,
                            sort=True,
                        )
                    )
                }
            ),
        )

    def _begin_login(self, country: str) -> ConfigFlowResult:
        self._authorize_url, self._challenge = auth.build_authorize_url(country)
        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema({vol.Required("redirect_url"): str}),
            description_placeholders={"authorize_url": self._authorize_url},
        )

    async def async_step_auth(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2: user pastes the miele:// redirect; exchange it for tokens."""
        errors: dict[str, str] = {}
        if user_input is not None and self._challenge is not None:
            session = async_get_clientsession(self.hass)
            try:
                code = auth.parse_redirect(user_input["redirect_url"], self._challenge["state"])
                self._tokens = await auth.async_exchange_code(session, self._challenge, code)
            except ValueError:
                errors["base"] = "auth_failed"
            else:
                if self._reauth_entry is not None:
                    return self._finish_reauth()
                return await self.async_step_pick()

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema({vol.Required("redirect_url"): str}),
            description_placeholders={"authorize_url": self._authorize_url},
            errors=errors,
        )

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 3: discover the appliance and create the entry."""
        assert self._tokens is not None
        session = async_get_clientsession(self.hass)
        try:
            mac = await MieleCloud(session, self._tokens).discover_mac()
        except MieleApiError:
            return self.async_abort(reason="no_appliance")

        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Miele wine cabinet ({mac})",
            data={CONF_TOKENS: self._tokens, CONF_MAC: mac, CONF_COUNTRY: self._challenge["cc"]},
        )

    # --- reauthentication ------------------------------------------------
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Triggered when the token can no longer be refreshed (e.g. password change)."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        country = (self._reauth_entry.data.get(CONF_COUNTRY) if self._reauth_entry else None) or "be"
        return self._begin_login(country)

    def _finish_reauth(self) -> ConfigFlowResult:
        assert self._reauth_entry is not None and self._tokens is not None
        return self.async_update_reload_and_abort(
            self._reauth_entry,
            data={**self._reauth_entry.data, CONF_TOKENS: self._tokens},
            reason="reauth_successful",
        )


class MieleWineOptionsFlow(OptionsFlow):
    """Polling options: how often to poll, and whether to adapt that interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Single-step form; saving triggers the entry reload in __init__.py."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_ADAPTIVE: user_input[CONF_ADAPTIVE],
                }
            )

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        # Entries predating this flow have no options; fall back to the
                        # interval the integration always used.
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(
                        NumberSelector(
                            NumberSelectorConfig(
                                min=MIN_SCAN_INTERVAL,
                                max=MAX_SCAN_INTERVAL,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="seconds",
                            )
                        ),
                        # NumberSelector hands back a float; the coordinator wants ints.
                        vol.Coerce(int),
                    ),
                    vol.Required(
                        CONF_ADAPTIVE,
                        default=options.get(CONF_ADAPTIVE, DEFAULT_ADAPTIVE),
                    ): BooleanSelector(),
                }
            ),
        )
