"""The setup dialog against a real Home Assistant core (pytest-homeassistant-custom-component).

    pip install pytest-homeassistant-custom-component
    pytest tests/test_config_flow.py

The NuaSense API is replaced by a stub; Home Assistant's registries, states and
config flow machinery are the real ones.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nuasense.const import CONF_CROPS, CONF_FORWARD, CONF_STATION_ID, DOMAIN
from custom_components.nuasense.forward import to_query

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


class StubApi:
    """What the dialog asks of NuaSense."""

    created: list[dict[str, Any]] = []
    stations_on_account: list[dict[str, Any]] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def stations(self) -> list[dict[str, Any]]:
        return list(self.stations_on_account)

    async def create_station(self, station_id, name, latitude, longitude, altitude_m):
        StubApi.created.append({"station_id": station_id, "name": name, "latitude": latitude, "longitude": longitude, "altitude_m": altitude_m})
        return {"station_id": station_id}

    async def push_token(self, station_id):
        return "/station/kw7n-4hpd-x2vt"


def _ecowitt_station(hass: HomeAssistant) -> str:
    """An Ecowitt gateway as the Ecowitt integration registers it."""
    source = MockConfigEntry(domain="ecowitt", data={})
    source.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("ecowitt", "GW2000A")}, name="GW2000A", manufacturer="Ecowitt"
    )
    ents = er.async_get(hass)
    sensors = [
        ("outdoor_temperature", "temperature", "°C", "21.4"),
        ("indoor_temperature", "temperature", "°C", "25.0"),
        ("outdoor_humidity", "humidity", "%", "63"),
        ("absolute_pressure", "atmospheric_pressure", "hPa", "815.6"),
        ("wind_speed", "wind_speed", "km/h", "11.5"),
        ("wind_gust", "wind_speed", "km/h", "22.0"),
        ("wind_direction", None, "°", "270"),
        ("rain_rate", "precipitation_intensity", "mm/h", "0"),
        ("daily_rain", "precipitation", "mm", "4.2"),
        ("solar_radiation", "irradiance", "W/m²", "500"),
    ]
    for key, dc, unit, value in sensors:
        entry = ents.async_get_or_create(
            "sensor", "ecowitt", f"gw2000a_{key}", device_id=dev.id, config_entry=source,
            original_device_class=dc, unit_of_measurement=unit, original_name=key.replace("_", " ").title(),
        )
        hass.states.async_set(entry.entity_id, value, {"unit_of_measurement": unit, "device_class": dc, "friendly_name": f"GW2000A {key.replace('_', ' ').title()}"})
    return dev.id


@pytest.fixture(autouse=True)
def verify_cleanup(event_loop):
    """The harness's own check, without its thread rule.

    Once an entry is saved, Home Assistant's executor shutdown leaves a thread
    named "_run_safe_shutdown_loop" behind on Python 3.12, which the harness
    (2025.1) counts as a leak. Lingering tasks still fail the test.
    """
    import asyncio

    before = asyncio.all_tasks(event_loop)
    yield
    event_loop.run_until_complete(event_loop.shutdown_default_executor())
    left = asyncio.all_tasks(event_loop) - before
    for task in left:
        task.cancel()
    assert not left, f"lingering tasks: {left}"


async def test_send_a_station_home_assistant_already_has(hass: HomeAssistant) -> None:
    StubApi.created = []
    StubApi.stations_on_account = []
    hass.config.latitude, hass.config.longitude, hass.config.elevation = -0.42, 36.95, 1890
    device_id = _ecowitt_station(hass)

    with patch("custom_components.nuasense.config_flow.NuaSenseApi", StubApi), patch(
        "custom_components.nuasense.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "nua_live_test"})
        # No station on the account: straight to the station Home Assistant has.
        assert result["type"] is FlowResultType.FORM and result["step_id"] == "ha_station", result
        assert device_id in result["data_schema"].schema["device"].container

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device": device_id})
        assert result["step_id"] == "ha_sensors"
        defaults = {str(k): k.default() for k in result["data_schema"].schema if hasattr(k, "default") and callable(k.default)}
        reg = er.async_get(hass)
        eid = lambda key: reg.async_get_entity_id("sensor", "ecowitt", f"gw2000a_{key}")
        assert defaults["temperature"] == eid("outdoor_temperature")
        assert defaults["humidity"] == eid("outdoor_humidity")
        assert defaults["rain"] == eid("daily_rain")
        assert defaults["pressure"] == eid("absolute_pressure")
        assert defaults["wind_direction"] == eid("wind_direction")

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**defaults, "plant": "vegetables", "sprinkler_mm_per_h": 4, "advanced": True}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    data = result["data"]
    assert data[CONF_STATION_ID].startswith("ha-gw2000a-")
    assert StubApi.created[0]["latitude"] == -0.42 and StubApi.created[0]["altitude_m"] == 1890
    fwd = data[CONF_FORWARD]
    assert fwd["push_path"] == "/station/kw7n-4hpd-x2vt"
    assert fwd["rain_param"] == "dailyrainin" and fwd["pressure_param"] == "baromabsin"

    # What the forwarder would send from these states.
    states = {e: (hass.states.get(e).state, hass.states.get(e).attributes["unit_of_measurement"]) for e in fwd["entities"].values()}
    q = to_query(states, fwd["entities"], fwd["rain_param"], fwd["pressure_param"])
    assert q["tempf"] == "70.52" and q["humidity"] == "63.0" and q["dailyrainin"] == "0.165"
    assert q["baromabsin"] == "24.085" and q["winddir"] == "270" and q["solarradiation"] == "500.0"


async def test_account_station_and_ha_station_offer_a_choice(hass: HomeAssistant) -> None:
    StubApi.stations_on_account = [{"station_id": "north-field", "name": "North field"}]
    _ecowitt_station(hass)
    with patch("custom_components.nuasense.config_flow.NuaSenseApi", StubApi):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "nua_live_test"})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["station", "ha_station"]


async def test_no_station_anywhere_says_so(hass: HomeAssistant) -> None:
    StubApi.stations_on_account = []
    with patch("custom_components.nuasense.config_flow.NuaSenseApi", StubApi):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "nua_live_test"})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "no_stations"}


class StubRuntimeApi:
    """What a running entry asks of NuaSense, with the uploads recorded."""

    sent: list[tuple[str, dict[str, str]]] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def stations(self):
        return [{"station_id": "ha-gw2000a-abcd", "name": "GW2000A"}]

    async def first_look(self, _station_id):
        return {}

    async def latest_derived(self, _station_id):
        return None

    async def send_reading(self, path, params):
        StubRuntimeApi.sent.append((path, dict(params)))
        return 200

    risk_asked: list[str] = []

    async def disease_risk(self, _station_id, crop):
        StubRuntimeApi.risk_asked.append(crop)
        if crop == "tomato":
            return {"crop": "tomato", "judged": 2, "not_judged": 1, "hours_of_readings": 700, "threats": [
                {"threat": "tomato_late_blight", "name": "Tomato: Late Blight", "status": "judged", "risk_level": "High", "risk_percent": 72, "data_completeness_pct": 96, "what_to_check": "check leaves"},
                {"threat": "tomato_septoria", "name": "Tomato: Septoria", "status": "judged", "risk_level": "Low", "risk_percent": 10},
                {"threat": "tomato_root_knot", "name": "Tomato: Root knot", "status": "not_judged", "reason": "the station has not reported a soil temperature probe"},
            ]}
        return {"crop": crop, "judged": 0, "not_judged": 1, "threats": [{"threat": "x", "status": "not_judged", "reason": "no planting date"}]}


async def test_a_running_entry_uploads_and_stops_on_unload(hass: HomeAssistant) -> None:
    StubRuntimeApi.sent = []
    _ecowitt_station(hass)
    reg = er.async_get(hass)
    eid = lambda key: reg.async_get_entity_id("sensor", "ecowitt", f"gw2000a_{key}")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="GW2000A",
        unique_id=f"{DOMAIN}:ha-gw2000a-abcd",
        data={
            CONF_API_KEY: "nua_live_test", "base_url": "https://api.nuasense.com", CONF_STATION_ID: "ha-gw2000a-abcd",
            "plant": "lawn", "sprinkler_mm_per_h": 10.0, "advanced": False,
            CONF_FORWARD: {
                "push_path": "/station/kw7n-4hpd-x2vt",
                "entities": {"temperature": eid("outdoor_temperature"), "humidity": eid("outdoor_humidity"), "rain": eid("daily_rain")},
                "rain_param": "dailyrainin", "pressure_param": "baromin",
            },
        },
    )
    entry.add_to_hass(hass)
    with patch("custom_components.nuasense.NuaSenseApi", StubRuntimeApi):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert StubRuntimeApi.sent, "the first upload goes out at start"
        path, params = StubRuntimeApi.sent[0]
        assert path == "/station/kw7n-4hpd-x2vt"
        assert params["tempf"] == "70.52" and params["humidity"] == "63.0" and params["dailyrainin"] == "0.165"
        assert params["action"] == "updateraw" and params["softwaretype"].startswith("HomeAssistant-NuaSense/")
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_options_choose_crops(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Garden", data={CONF_API_KEY: "k", CONF_STATION_ID: "north-field"})
    entry.add_to_hass(hass)
    with patch("custom_components.nuasense.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM and result["step_id"] == "init"
        # The form itself refuses a crop without models.
        with pytest.raises(InvalidData):
            await hass.config_entries.options.async_configure(result["flow_id"], {CONF_CROPS: ["tomato", "not-a-crop"]})
        result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_CROPS: ["tomato", "potato"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_CROPS] == ["tomato", "potato"]


async def test_disease_risk_sensors_show_the_highest_judged_level(hass: HomeAssistant) -> None:
    StubRuntimeApi.risk_asked = []
    entry = MockConfigEntry(
        domain=DOMAIN, title="Garden", unique_id=f"{DOMAIN}:ha-gw2000a-abcd",
        data={CONF_API_KEY: "nua_live_test", "base_url": "https://api.nuasense.com", CONF_STATION_ID: "ha-gw2000a-abcd",
              "plant": "lawn", "sprinkler_mm_per_h": 10.0, "advanced": False},
        options={CONF_CROPS: ["tomato", "potato"]},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.nuasense.NuaSenseApi", StubRuntimeApi):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        reg = er.async_get(hass)
        tomato = reg.async_get_entity_id("sensor", DOMAIN, "ha-gw2000a-abcd_disease_risk_tomato")
        potato = reg.async_get_entity_id("sensor", DOMAIN, "ha-gw2000a-abcd_disease_risk_potato")
        assert tomato and potato
        t = hass.states.get(tomato)
        assert t.state == "high"
        assert t.attributes["threats"][0]["what_to_check"] == "check leaves"
        assert t.attributes["threats"][2]["status"] == "not_judged" and "level" not in t.attributes["threats"][2]
        assert hass.states.get(potato).state == "not_judged"
        assert sorted(StubRuntimeApi.risk_asked) == ["potato", "tomato"]
        # A second refresh within the hour asks NuaSense nothing new.
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_refresh()
        assert len(StubRuntimeApi.risk_asked) == 2
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
