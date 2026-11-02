"""Polls NuaSense for one station and keeps the latest answers."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NuaSenseApi, NuaSenseAuthError, NuaSenseError, NuaSenseNoPositionError
from .const import DOMAIN, SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)


class NuaSenseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One refresh = the station row, the first look and the latest hourly row."""

    def __init__(self, hass: HomeAssistant, api: NuaSenseApi, station_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {station_id}",
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
        )
        self.api = api
        self.station_id = station_id

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            stations = await self.api.stations()
        except NuaSenseAuthError as err:
            raise UpdateFailed(str(err)) from err
        except NuaSenseError as err:
            raise UpdateFailed(str(err)) from err

        station = next((s for s in stations if s.get("station_id") == self.station_id), None)
        if station is None:
            raise UpdateFailed(f"station {self.station_id} is no longer on this account")

        # A station without a position has no first look; that is a state to
        # show, not a failure to retry.
        first_look: dict[str, Any] | None
        try:
            first_look = await self.api.first_look(self.station_id)
        except NuaSenseNoPositionError:
            first_look = None
        except NuaSenseError as err:
            _LOGGER.debug("first look unavailable for %s: %s", self.station_id, err)
            first_look = None

        try:
            derived = await self.api.latest_derived(self.station_id)
        except NuaSenseError as err:
            _LOGGER.debug("derived values unavailable for %s: %s", self.station_id, err)
            derived = None

        return {"station": station, "first_look": first_look, "derived": derived}
