"""Config flow: consumer OAuth PKCE login (paste-back), plus reauth."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import auth
from .api import MieleApiError, MieleCloud
from .const import CONF_COUNTRY, CONF_MAC, CONF_TOKENS, DOMAIN


class MieleWineConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle initial login + reauthentication."""

    VERSION = 1

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
        self.hass.config_entries.async_update_entry(
            self._reauth_entry, data={**self._reauth_entry.data, CONF_TOKENS: self._tokens}
        )
        self.hass.async_create_task(
            self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
        )
        return self.async_abort(reason="reauth_successful")
