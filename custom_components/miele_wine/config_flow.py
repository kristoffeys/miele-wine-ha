"""Config flow: consumer OAuth PKCE login (paste-back), then pick the appliance."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import auth
from .api import MieleApiError, MieleCloud
from .const import CONF_COUNTRY, CONF_MAC, CONF_TOKENS, DOMAIN


class MieleWineConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the login + appliance setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._challenge: dict[str, str] | None = None
        self._tokens: dict[str, Any] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: choose country, generate the authorize URL."""
        if user_input is not None:
            url, self._challenge = auth.build_authorize_url(user_input[CONF_COUNTRY])
            self._authorize_url = url
            return await self.async_step_auth()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_COUNTRY, default="be"): str}),
        )

    async def async_step_auth(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2: user opens the URL, logs in, pastes the miele:// redirect back."""
        errors: dict[str, str] = {}
        if user_input is not None and self._challenge is not None:
            session = async_get_clientsession(self.hass)
            try:
                code = auth.parse_redirect(user_input["redirect_url"], self._challenge["state"])
                self._tokens = await auth.async_exchange_code(session, self._challenge, code)
            except ValueError as err:
                errors["base"] = "auth_failed"
                errors["redirect_url"] = str(err)[:60]
            else:
                return await self.async_step_pick()

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema({vol.Required("redirect_url"): str}),
            description_placeholders={"authorize_url": getattr(self, "_authorize_url", "")},
            errors=errors,
        )

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 3: discover the appliance and create the entry."""
        assert self._tokens is not None
        session = async_get_clientsession(self.hass)
        client = MieleCloud(session, self._tokens)
        try:
            mac = await client.discover_mac()
        except MieleApiError:
            return self.async_abort(reason="no_appliance")

        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Miele wine cabinet ({mac})",
            data={CONF_TOKENS: self._tokens, CONF_MAC: mac, CONF_COUNTRY: self._challenge["cc"]},
        )
