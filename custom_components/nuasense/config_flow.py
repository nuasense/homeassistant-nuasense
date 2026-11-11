"""Config flow: an API key, then which station and what the garden is.

The station is either one the NuaSense account already has, or a weather
station Home Assistant already shows (Ecowitt, Netatmo, Ambient, Tempest,
WeatherLink or any other with outdoor temperature and humidity). The second is
registered on the account in the dialog and its readings are sent every five
minutes, so nobody has to open the NuaSense console or write a forwarding rule.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
import random
import re

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import NuaSenseApi, NuaSenseAuthError, NuaSenseError
from .forward import ROLES, Candidate, pick, pressure_param_for, rain_key
from .const import (
    CONF_ADVANCED,
    CONF_BASE_URL,
    CONF_FORWARD,
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
        self._devices: dict[str, str] = {}
        self._device_id: str | None = None
        self._candidates: dict[str, Candidate] = {}

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
                self._auth = {
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    CONF_BASE_URL: user_input.get(CONF_BASE_URL) or DEFAULT_BASE_URL,
                }
                self._stations = stations
                self._devices = self._weather_devices()
                if stations and self._devices:
                    return await self.async_step_source()
                if stations:
                    return await self.async_step_station()
                if self._devices:
                    return await self.async_step_ha_station()
                errors["base"] = "no_stations"

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

    async def async_step_source(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A station on the NuaSense account, or one Home Assistant already shows."""
        return self.async_show_menu(step_id="source", menu_options=["station", "ha_station"])

    # --- a station Home Assistant already has --------------------------------------

    def _sensor_candidates(self) -> dict[str, list[Candidate]]:
        """Sensor entities per device, with what Home Assistant knows about each."""
        ent_reg = er.async_get(self.hass)
        out: dict[str, list[Candidate]] = {}
        for entry in ent_reg.entities.values():
            if entry.domain != "sensor" or not entry.device_id or entry.disabled_by:
                continue
            state = self.hass.states.get(entry.entity_id)
            unit = (state.attributes.get("unit_of_measurement") if state else None) or entry.unit_of_measurement
            name = (state.name if state else None) or entry.name or entry.original_name or entry.entity_id
            out.setdefault(entry.device_id, []).append(
                Candidate(entry.entity_id, entry.device_class or entry.original_device_class, unit, str(name))
            )
        return out

    def _weather_devices(self) -> dict[str, str]:
        """Devices with an outdoor temperature and humidity: the stations Home Assistant has."""
        dev_reg = dr.async_get(self.hass)
        found: dict[str, str] = {}
        for device_id, cands in self._sensor_candidates().items():
            picked = pick(cands)
            if "temperature" in picked and "humidity" in picked:
                device = dev_reg.async_get(device_id)
                if device is None:
                    continue
                label = device.name_by_user or device.name or device_id
                if device.manufacturer:
                    label = f"{label} ({device.manufacturer})"
                found[device_id] = label
        return found

    async def async_step_ha_station(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._device_id = user_input["device"]
            return await self.async_step_ha_sensors()
        return self.async_show_form(
            step_id="ha_station",
            data_schema=vol.Schema({vol.Required("device"): vol.In(self._devices)}),
        )

    async def async_step_ha_sensors(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        per_device = self._sensor_candidates()
        own = per_device.get(self._device_id or "", [])
        # Sensors of the same integration on other devices (Netatmo puts the rain gauge
        # and the anemometer on devices of their own) fill what the station lacks.
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get(self._device_id) if self._device_id else None
        siblings: list[Candidate] = []
        if device is not None:
            for other_id, cands in per_device.items():
                other = dev_reg.async_get(other_id)
                if other_id != self._device_id and other is not None and other.config_entries & device.config_entries:
                    siblings.extend(cands)
        defaults = {**pick(siblings), **pick(own)}
        self._candidates = {c.entity_id: c for c in own + siblings}

        if user_input is not None:
            chosen = {role: user_input[role] for role in ROLES if user_input.get(role)}
            if "temperature" not in chosen or "humidity" not in chosen:
                errors["base"] = "need_temperature_humidity"
            else:
                rain_c = self._candidates.get(chosen.get("rain", "")) or self._candidate_for(chosen.get("rain"))
                pressure_c = self._candidates.get(chosen.get("pressure", "")) or self._candidate_for(chosen.get("pressure"))
                rain_param = rain_key(rain_c) if rain_c else None
                if chosen.get("rain") and rain_param is None:
                    chosen.pop("rain")  # a rate, not a running total: not sent
                label = self._devices.get(self._device_id or "", "Home Assistant station").split(" (")[0]
                station_id = self._new_station_id(label)
                api = NuaSenseApi(async_get_clientsession(self.hass), self._auth[CONF_API_KEY], self._auth[CONF_BASE_URL])
                try:
                    await api.create_station(
                        station_id,
                        label,
                        self.hass.config.latitude,
                        self.hass.config.longitude,
                        float(self.hass.config.elevation) if self.hass.config.elevation is not None else None,
                    )
                    push_path = await api.push_token(station_id)
                except NuaSenseAuthError:
                    errors["base"] = "key_cannot_write"
                except NuaSenseError as err:
                    errors["base"] = "station_limit" if "limit" in str(err).lower() else "cannot_connect"
                else:
                    await self.async_set_unique_id(f"{DOMAIN}:{station_id}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=label,
                        data={
                            **self._auth,
                            CONF_STATION_ID: station_id,
                            CONF_PLANT: user_input[CONF_PLANT],
                            CONF_SPRINKLER_RATE: float(user_input[CONF_SPRINKLER_RATE]),
                            CONF_ADVANCED: bool(user_input[CONF_ADVANCED]),
                            CONF_FORWARD: {
                                "push_path": push_path,
                                "entities": chosen,
                                "rain_param": rain_param,
                                "pressure_param": pressure_param_for(pressure_c),
                            },
                        },
                    )

        sensor = EntitySelector(EntitySelectorConfig(domain="sensor"))
        fields: dict[Any, Any] = {}
        for role in ROLES:
            key = vol.Required(role, default=defaults[role]) if role in ("temperature", "humidity") and role in defaults else (
                vol.Optional(role, default=defaults[role]) if role in defaults else vol.Optional(role)
            )
            fields[key] = sensor
        fields[vol.Required(CONF_PLANT, default=DEFAULT_PLANT)] = SelectSelector(
            SelectSelectorConfig(options=PLANTS, translation_key="plant", mode=SelectSelectorMode.DROPDOWN)
        )
        fields[vol.Required(CONF_SPRINKLER_RATE, default=DEFAULT_SPRINKLER_RATE)] = vol.All(vol.Coerce(float), vol.Range(min=0, max=100))
        fields[vol.Required(CONF_ADVANCED, default=False)] = bool
        return self.async_show_form(
            step_id="ha_sensors",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={"station": self._devices.get(self._device_id or "", "")},
        )

    def _candidate_for(self, entity_id: str | None) -> Candidate | None:
        """A sensor picked by hand from outside the device, described from its state."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return Candidate(entity_id, state.attributes.get("device_class"), state.attributes.get("unit_of_measurement"), state.name)

    def _new_station_id(self, label: str) -> str:
        """The name as a slug plus four letters, so two "Garden" stations do not collide."""
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "station"
        tail = "".join(random.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(4))
        known = {s.get("station_id") for s in self._stations}
        candidate = f"ha-{slug}-{tail}"
        return candidate if candidate not in known else f"ha-{slug}-{tail}x"

