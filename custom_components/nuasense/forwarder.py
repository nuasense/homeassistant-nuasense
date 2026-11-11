"""Sends a weather station Home Assistant already has to NuaSense, every five minutes."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .api import NuaSenseApi, NuaSenseError
from .const import FORWARD_INTERVAL_SECONDS
from .forward import to_query

_LOGGER = logging.getLogger(__name__)
VERSION_TAG = "HomeAssistant-NuaSense"


class StationForwarder:
    """Reads the chosen sensors' states and uploads them to the station's NuaSense address."""

    def __init__(self, hass: HomeAssistant, api: NuaSenseApi, forward: dict[str, Any], version: str) -> None:
        self._hass = hass
        self._api = api
        self._path = forward["push_path"]
        self._entities: dict[str, str] = dict(forward.get("entities") or {})
        self._rain_param = forward.get("rain_param")
        self._pressure_param = forward.get("pressure_param") or "baromin"
        self._software = f"{VERSION_TAG}/{version}"
        self._unsub = None
        self._failing = False

    def start(self) -> None:
        self._unsub = async_track_time_interval(self._hass, self._tick, timedelta(seconds=FORWARD_INTERVAL_SECONDS))
        self._hass.async_create_task(self._send())

    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _tick(self, _now) -> None:
        await self._send()

    async def _send(self) -> None:
        states: dict[str, tuple[Any, str | None]] = {}
        for entity_id in self._entities.values():
            st = self._hass.states.get(entity_id)
            if st is not None:
                states[entity_id] = (st.state, st.attributes.get("unit_of_measurement"))
        params = to_query(states, self._entities, self._rain_param, self._pressure_param)
        if not params:
            return
        params.update({"action": "updateraw", "softwaretype": self._software, "dateutc": "now"})
        try:
            status = await self._api.send_reading(self._path, params)
        except NuaSenseError as err:
            self._report(f"upload to NuaSense failed: {err}")
            return
        if status >= 400:
            self._report(f"NuaSense refused the upload (HTTP {status})")
        elif self._failing:
            _LOGGER.info("uploads to NuaSense work again")
            self._failing = False

    def _report(self, text: str) -> None:
        # Once per outage, not every five minutes.
        if not self._failing:
            _LOGGER.warning(text)
        self._failing = True
