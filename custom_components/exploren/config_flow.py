"""Config flow for the Exploren integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ExplorenApi, ExplorenAuthError, ExplorenError
from .const import CONF_TOKEN, DOMAIN

USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
)
PASSWORD_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class ExplorenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Exploren config flow.

    The password is never stored: only the email and the OAuth token bundle are
    persisted. When the refresh token dies HA raises reauth automatically; the
    entry can also be reconfigured manually at any time.
    """

    VERSION = 1

    _entry: ConfigEntry | None = None

    async def _authenticate(
        self, email: str, password: str
    ) -> tuple[dict | None, str | None]:
        """Return (token, error_code)."""
        api = ExplorenApi(
            async_get_clientsession(self.hass), email=email, password=password
        )
        try:
            token = await api.login()
        except ExplorenAuthError:
            return None, "invalid_auth"
        except ExplorenError:
            return None, "cannot_connect"
        except Exception:  # noqa: BLE001 - surface as a generic error to the UI
            return None, "unknown"
        return token, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            token, error = await self._authenticate(email, user_input[CONF_PASSWORD])
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(email.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=email,
                    data={CONF_EMAIL: email, CONF_TOKEN: token},
                )
        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    # -- reauth (automatic, triggered by ConfigEntryAuthFailed) -------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._entry
        assert entry is not None
        if user_input is not None:
            token, error = await self._authenticate(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if error:
                errors["base"] = error
            else:
                await self._update_and_reload(entry, entry.data[CONF_EMAIL], token)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=PASSWORD_SCHEMA,
            description_placeholders={CONF_EMAIL: entry.data[CONF_EMAIL]},
            errors=errors,
        )

    # -- reconfigure (manual, from the entry's menu) ------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            token, error = await self._authenticate(email, user_input[CONF_PASSWORD])
            if error:
                errors["base"] = error
            elif entry.unique_id and entry.unique_id != email.lower():
                errors["base"] = "wrong_account"
            else:
                await self._update_and_reload(entry, email, token)
                return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_EMAIL: entry.data.get(CONF_EMAIL)}
            ),
            errors=errors,
        )

    async def _update_and_reload(
        self, entry: ConfigEntry, email: str, token: dict | None
    ) -> None:
        """Persist the new email/token (no password) and reload the entry."""
        self.hass.config_entries.async_update_entry(
            entry,
            title=email,
            unique_id=email.lower(),
            data={CONF_EMAIL: email, CONF_TOKEN: token},
        )
        await self.hass.config_entries.async_reload(entry.entry_id)
