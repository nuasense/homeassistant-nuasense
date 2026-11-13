"""Sensors for one station: house & garden first, agronomy on request."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPressure, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTRIBUTION,
    CONF_ADVANCED,
    CONF_CROPS,
    CROPS,
    CONF_PLANT,
    CONF_SPRINKLER_RATE,
    DEFAULT_PLANT,
    DEFAULT_SPRINKLER_RATE,
    DOMAIN,
)
from .coordinator import NuaSenseCoordinator
from .quality import STATES as QUALITY_STATES, quality_attributes, quality_of, quality_state

Config = dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class NuaSenseSensorDescription(SensorEntityDescription):
    """A sensor and how to read it out of the coordinator's data."""

    value: Callable[[dict[str, Any], Config], Any]
    attributes: Callable[[dict[str, Any], Config], dict[str, Any]] | None = None


def _look(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("first_look") or {}


def _tonight(data: dict[str, Any]) -> dict[str, Any]:
    return _look(data).get("tonight") or {}


def _spray(data: dict[str, Any]) -> dict[str, Any]:
    return _look(data).get("spray") or {}


def _plausibility(data: dict[str, Any]) -> dict[str, Any]:
    look = _look(data)
    return look.get("plausibility") or look.get("station_check") or {}


def _watering(data: dict[str, Any]) -> dict[str, Any]:
    return (_look(data).get("garden") or {}).get("watering") or {}


def _derived(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("derived") or {}


def _need_mm(data: dict[str, Any], cfg: Config) -> float | None:
    need = _watering(data).get("need_mm")
    if not isinstance(need, dict):
        return None
    value = need.get(cfg.get(CONF_PLANT, DEFAULT_PLANT))
    return value if isinstance(value, (int, float)) else None


def _need_minutes(data: dict[str, Any], cfg: Config) -> int | None:
    mm = _need_mm(data, cfg)
    rate = float(cfg.get(CONF_SPRINKLER_RATE, DEFAULT_SPRINKLER_RATE) or 0)
    if mm is None or rate <= 0:
        return None
    return round(mm / rate * 60)


def _spray_window_text(data: dict[str, Any], _cfg: Config) -> str | None:
    spray = _spray(data)
    if not spray:
        return None
    window = spray.get("window")
    if window:
        return f"{window.get('from')}–{window.get('to')}"
    return "none"


def _last_upload(data: dict[str, Any], _cfg: Config) -> datetime | None:
    push = (data.get("station") or {}).get("push") or {}
    raw = push.get("last_push_at")
    return dt_util.parse_datetime(raw) if raw else None


# House & garden: what every station gets.
GARDEN: tuple[NuaSenseSensorDescription, ...] = (
    NuaSenseSensorDescription(
        key="tonight_low",
        name="Tonight's low",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value=lambda d, c: _tonight(d).get("low_c"),
        attributes=lambda d, c: {"at": _tonight(d).get("at"), "grass_level_c": _tonight(d).get("grass_low_c")},
    ),
    NuaSenseSensorDescription(
        key="tonight_frost",
        name="Frost tonight",
        icon="mdi:snowflake-thermometer",
        value=lambda d, c: _tonight(d).get("frost"),
    ),
    NuaSenseSensorDescription(
        key="watering_mm",
        name="Watering today",
        native_unit_of_measurement="mm",
        icon="mdi:sprinkler-variant",
        value=_need_mm,
        attributes=lambda d, c: {
            "plant": c.get(CONF_PLANT, DEFAULT_PLANT),
            "et0_mm": _watering(d).get("et0_mm"),
            "et0_source": _watering(d).get("et0_source"),
            "rain_last_24h_mm": _watering(d).get("rain_last_24h_mm"),
            "rain_next_24h_mm": _watering(d).get("rain_next_24h_mm"),
        },
    ),
    NuaSenseSensorDescription(
        key="watering_minutes",
        name="Watering time today",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-outline",
        value=_need_minutes,
        attributes=lambda d, c: {"sprinkler_mm_per_h": c.get(CONF_SPRINKLER_RATE, DEFAULT_SPRINKLER_RATE)},
    ),
    NuaSenseSensorDescription(
        key="rain_next_24h",
        name="Rain next 24 h",
        native_unit_of_measurement="mm",
        icon="mdi:weather-rainy",
        value=lambda d, c: _watering(d).get("rain_next_24h_mm"),
    ),
    NuaSenseSensorDescription(
        key="plausibility",
        name="Plausibility",
        icon="mdi:check-decagram-outline",
        value=lambda d, c: _plausibility(d).get("verdict"),
        attributes=lambda d, c: {
            "reading_c": _plausibility(d).get("reading_c"),
            "model_c": _plausibility(d).get("model_c"),
            "difference_c": _plausibility(d).get("diff_c"),
            "threshold_c": _plausibility(d).get("threshold_c"),
        },
    ),
    NuaSenseSensorDescription(
        key="data_quality",
        name="Data quality",
        icon="mdi:shield-check-outline",
        device_class=SensorDeviceClass.ENUM,
        options=QUALITY_STATES,
        value=lambda d, c: quality_state(quality_of(d)),
        attributes=lambda d, c: quality_attributes(quality_of(d)),
    ),
    NuaSenseSensorDescription(
        key="last_upload",
        name="Last upload",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=_last_upload,
        attributes=lambda d, c: {"device": ((d.get("station") or {}).get("push") or {}).get("device")},
    ),
)

# Agronomy: only when "advanced" is switched on.
ADVANCED: tuple[NuaSenseSensorDescription, ...] = (
    NuaSenseSensorDescription(
        key="spray_window",
        name="Next spray window",
        icon="mdi:spray",
        value=_spray_window_text,
        attributes=lambda d, c: {
            "date": _spray(d).get("date"),
            "wind_max_ms": _spray(d).get("wind_max_ms"),
            "reason": _spray(d).get("reason"),
        },
    ),
    NuaSenseSensorDescription(
        key="et0_hour",
        name="ET0 last hour",
        native_unit_of_measurement="mm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-outline",
        value=lambda d, c: _derived(d).get("et0_hour"),
    ),
    NuaSenseSensorDescription(
        key="leaf_wetness_hours",
        name="Leaf wetness, consecutive hours",
        native_unit_of_measurement="h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:leaf",
        value=lambda d, c: _derived(d).get("lwd_consecutive_hours"),
        attributes=lambda d, c: {"reason": _derived(d).get("lwd_reason")},
    ),
    NuaSenseSensorDescription(
        key="spray_quality",
        name="Spray quality",
        icon="mdi:weather-windy",
        value=lambda d, c: _derived(d).get("spray_quality_label"),
        attributes=lambda d, c: {
            "index": _derived(d).get("spray_quality_index"),
            "limiting_factor": _derived(d).get("spray_limiting_factor"),
            "inversion_risk": _derived(d).get("inversion_risk"),
        },
    ),
    NuaSenseSensorDescription(
        key="vpd",
        name="Vapour pressure deficit",
        native_unit_of_measurement="kPa",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value=lambda d, c: _derived(d).get("vpd"),
    ),
    NuaSenseSensorDescription(
        key="delta_t",
        name="Delta T",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        value=lambda d, c: _derived(d).get("delta_t"),
    ),
    NuaSenseSensorDescription(
        key="temperature",
        name="Temperature, hourly mean",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d, c: _derived(d).get("temperature"),
    ),
    NuaSenseSensorDescription(
        key="humidity",
        name="Humidity, hourly mean",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d, c: _derived(d).get("humidity"),
    ),
    NuaSenseSensorDescription(
        key="pressure",
        name="Pressure, hourly mean",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d, c: _derived(d).get("pressure"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: NuaSenseCoordinator = hass.data[DOMAIN][entry.entry_id]
    cfg: Config = dict(entry.data)
    descriptions = list(GARDEN)
    if float(cfg.get(CONF_SPRINKLER_RATE, DEFAULT_SPRINKLER_RATE) or 0) <= 0:
        descriptions = [d for d in descriptions if d.key != "watering_minutes"]
    if cfg.get(CONF_ADVANCED):
        descriptions += list(ADVANCED)
    entities: list[SensorEntity] = [NuaSenseSensor(coordinator, entry, cfg, d) for d in descriptions]
    crops = [c for c in entry.options.get(CONF_CROPS, []) if c in CROPS]
    entities += [NuaSenseRiskSensor(coordinator, entry, crop) for crop in crops]
    async_add_entities(entities)


class NuaSenseSensor(CoordinatorEntity[NuaSenseCoordinator], SensorEntity):
    """One value NuaSense computes for the station."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    entity_description: NuaSenseSensorDescription

    def __init__(
        self,
        coordinator: NuaSenseCoordinator,
        entry: ConfigEntry,
        cfg: Config,
        description: NuaSenseSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._cfg = cfg
        self._attr_unique_id = f"{coordinator.station_id}_{description.key}"
        station = coordinator.data.get("station") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.station_id)},
            name=entry.title,
            manufacturer="NuaSense",
            model="External station",
            configuration_url="https://platform.nuasense.com/stations",
            hw_version=(station.get("push") or {}).get("device"),
        )

    @property
    def native_value(self) -> Any:
        try:
            return self.entity_description.value(self.coordinator.data, self._cfg)
        except (TypeError, ValueError, AttributeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        try:
            attrs = self.entity_description.attributes(self.coordinator.data, self._cfg)
        except (TypeError, ValueError, AttributeError):
            return None
        return {k: v for k, v in attrs.items() if v is not None}


# --- disease and pest risk, one sensor per chosen crop ---------------------------

RISK_STATES = ["high", "medium", "low", "not_judged"]
_LEVEL_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def risk_state(body: dict[str, Any] | None) -> str | None:
    """The highest level among the threats NuaSense could judge; "not_judged" when none."""
    if not isinstance(body, dict):
        return None
    threats = body.get("threats")
    if not isinstance(threats, list):
        return None
    judged = [
        t for t in threats
        if isinstance(t, dict) and t.get("status") in ("judged", "thin_data") and t.get("risk_level") in _LEVEL_ORDER
    ]
    if not judged:
        return "not_judged"
    top = min(judged, key=lambda t: _LEVEL_ORDER[t["risk_level"]])
    return str(top["risk_level"]).lower()


def risk_attributes(body: dict[str, Any] | None) -> dict[str, Any]:
    """Each threat in a line a person reads; the ones not judged say why."""
    if not isinstance(body, dict):
        return {}
    rows = []
    for t in body.get("threats") or []:
        if not isinstance(t, dict):
            continue
        row = {"threat": t.get("name") or t.get("threat"), "status": t.get("status")}
        if t.get("risk_level"):
            row["level"] = str(t["risk_level"]).lower()
            row["percent"] = t.get("risk_percent")
            row["data_completeness_pct"] = t.get("data_completeness_pct")
        if t.get("what_to_check"):
            row["what_to_check"] = t["what_to_check"]
        if t.get("reason"):
            row["reason"] = t["reason"]
        rows.append(row)
    return {
        "threats": rows,
        "judged": body.get("judged"),
        "not_judged": body.get("not_judged"),
        "hours_of_readings": body.get("hours_of_readings"),
        "note": body.get("note"),
    }


class NuaSenseRiskSensor(CoordinatorEntity[NuaSenseCoordinator], SensorEntity):
    """Disease and pest risk for one crop, from the station's own hourly weather."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = RISK_STATES
    _attr_translation_key = "disease_risk"
    _attr_icon = "mdi:sprout-outline"

    def __init__(self, coordinator: NuaSenseCoordinator, entry: ConfigEntry, crop: str) -> None:
        super().__init__(coordinator)
        self._crop = crop
        self._attr_unique_id = f"{coordinator.station_id}_disease_risk_{crop}"
        self._attr_name = f"Disease risk, {crop.replace('_', ' ')}"
        station = coordinator.data.get("station") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.station_id)},
            name=entry.title,
            manufacturer="NuaSense",
            model="External station",
            configuration_url="https://platform.nuasense.com/stations",
            hw_version=(station.get("push") or {}).get("device"),
        )

    def _body(self) -> dict[str, Any] | None:
        return ((self.coordinator.data or {}).get("risk") or {}).get(self._crop)

    @property
    def native_value(self) -> str | None:
        return risk_state(self._body())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs = risk_attributes(self._body())
        return {k: v for k, v in attrs.items() if v is not None} or None
