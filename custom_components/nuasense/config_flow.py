"""Config flow: an API key, then which station and what the garden is."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import NuaSenseApi, NuaSenseAuthError, NuaSenseError
from .const import (
    CONF_ADVANCED,
    CONF_BASE_URL,
    CONF_PLANT,
    CONF_SPRINKLER_RATE,
    CONF_STATION_ID,
    DEFAULT_BASE_URL,
    DEFAULT_PLANT,
    DEFAULT_SPRINKLER_RATE,
    DOMAIN,
    PLANTS,
)


class NuaSenseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two steps: prove the key works, then pick the station and the garden."""

    VERSION = 1

    def __init__(self) -> None:
        self._auth: dict[str, Any] = {}
        self._stations: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api = NuaSenseApi(
                async_get_clientsession(self.hass),
                user_input[CONF_API_KEY],
                user_input.get(CONF_BASE_URL) or DEFAULT_BASE_URL,
            )
            try:
                stations = await api.stations()
            except NuaSenseAuthError:
                errors["base"] = "invalid_auth"
            except NuaSenseError:
                errors["base"] = "cannot_connect"
            else:
                if not stations:
                    errors["base"] = "no_stations"
                else:
                    self._auth = {
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_BASE_URL: user_input.get(CONF_BASE_URL) or DEFAULT_BASE_URL,
                    }
                    self._stations = stations
                    return await self.async_step_station()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                }
            ),
            errors=errors,
        )

    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            station_id = user_input[CONF_STATION_ID]
            await self.async_set_unique_id(f"{DOMAIN}:{station_id}")
            self._abort_if_unique_id_configured()
            name = next(
                (s.get("name") or s["station_id"] for s in self._stations if s.get("station_id") == station_id),
                station_id,
            )
            return self.async_create_entry(
                title=name,
                data={
                    **self._auth,
                    CONF_STATION_ID: station_id,
                    CONF_PLANT: user_input[CONF_PLANT],
                    CONF_SPRINKLER_RATE: float(user_input[CONF_SPRINKLER_RATE]),
                    CONF_ADVANCED: bool(user_input[CONF_ADVANCED]),
                },
            )

        options = {s["station_id"]: (s.get("name") or s["station_id"]) for s in self._stations}
        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): vol.In(options),
                    vol.Required(CONF_PLANT, default=DEFAULT_PLANT): SelectSelector(
                        SelectSelectorConfig(
                            options=PLANTS, translation_key="plant", mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                    vol.Required(CONF_SPRINKLER_RATE, default=DEFAULT_SPRINKLER_RATE): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=100)
                    ),
                    vol.Required(CONF_ADVANCED, default=False): bool,
                }
            ),
        )
