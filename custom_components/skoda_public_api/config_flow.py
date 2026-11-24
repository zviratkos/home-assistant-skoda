"""Config flow: API key + VIN (one entry per vehicle), reauth, reconfigure, options."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    SkodaApiError,
    SkodaAuthError,
    SkodaConnectionError,
    SkodaData,
    SkodaNotFoundError,
    SkodaPublicApi,
    SkodaRateLimitError,
)
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_VIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class SkodaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, api_key: str, vin: str) -> tuple[SkodaData | None, str | None]:
        """Do one real request; returns (data, error_key)."""
        api = SkodaPublicApi(async_get_clientsession(self.hass), api_key, vin)
        try:
            return await api.async_get_vehicle(), None
        except SkodaAuthError:
            return None, "invalid_auth"
        except SkodaNotFoundError:
            return None, "vehicle_not_found"
        except SkodaRateLimitError:
            return None, "rate_limited"
        except SkodaConnectionError:
            return None, "cannot_connect"
        except SkodaApiError:
            _LOGGER.exception("Unexpected API error during validation")
            return None, "unknown"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            vin = user_input[CONF_VIN].strip().upper()
            key = user_input[CONF_API_KEY].strip()
            if not VIN_RE.match(vin):
                errors[CONF_VIN] = "invalid_vin"
            else:
                await self.async_set_unique_id(vin)
                self._abort_if_unique_id_configured()
                data, error = await self._validate(key, vin)
                if error:
                    errors["base"] = error
                else:
                    name = (data.vehicle.get("name") if data else None) or f"Škoda ...{vin[-6:]}"
                    return self.async_create_entry(
                        title=name, data={CONF_API_KEY: key, CONF_VIN: vin}
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_KEY): KEY_SELECTOR, vol.Required(CONF_VIN): str}
            ),
            errors=errors,
        )

    # --- replace an expired / soon-to-expire key ---
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._new_key("reauth_confirm", self._get_reauth_entry(), "reauth_successful", user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._new_key("reconfigure", self._get_reconfigure_entry(), "reconfigure_successful", user_input)

    async def _new_key(self, step_id: str, entry, done_reason: str, user_input) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            _, error = await self._validate(key, entry.data[CONF_VIN])
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: key}, reason=done_reason
                )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): KEY_SELECTOR}),
            description_placeholders={"vin": entry.data[CONF_VIN]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> SkodaOptionsFlow:
        return SkodaOptionsFlow()


class SkodaOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
