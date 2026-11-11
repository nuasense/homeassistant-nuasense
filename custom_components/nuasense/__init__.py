"""NuaSense: what your weather station means for your crop, in Home Assistant.

One config entry per external station on a NuaSense account. A station Home
Assistant already had is also sent to NuaSense every five minutes. The entry polls
the first look (tonight's low, the next spray window, the latest reading
against the model) and the latest hourly values (ET0, leaf wetness, spray
quality) and exposes them as sensors.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NuaSenseApi
from .const import CONF_BASE_URL, CONF_FORWARD, CONF_STATION_ID, DEFAULT_BASE_URL, DOMAIN, INTEGRATION_VERSION
from .coordinator import NuaSenseCoordinator
from .forwarder import StationForwarder

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start polling for this station."""
    api = NuaSenseApi(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY],
        entry.data.get(CONF_BASE_URL) or DEFAULT_BASE_URL,
    )
    # A station Home Assistant already had is sent to NuaSense first, so the
    # first look has readings to work from.
    forward = entry.data.get(CONF_FORWARD)
    if isinstance(forward, dict) and forward.get("push_path"):
        forwarder = StationForwarder(hass, api, forward, INTEGRATION_VERSION)
        forwarder.start()
        entry.async_on_unload(forwarder.stop)

    coordinator = NuaSenseCoordinator(hass, api, entry.data[CONF_STATION_ID])
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop polling for this station."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded
