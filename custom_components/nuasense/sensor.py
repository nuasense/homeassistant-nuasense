"""Sensors: the first look and the latest hourly values for one station."""

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
from homeassistant.const import PERCENTAGE, UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN
from .coordinator import NuaSenseCoordinator


@dataclass(frozen=True, kw_only=True)
class NuaSenseSensorDescription(SensorEntityDescription):
    """A sensor and how to read it out of the coordinator's data."""

    value: Callable[[dict[str, Any]], Any]
    attributes: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _look(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("first_look") or {}


def _tonight(data: dict[str, Any]) -> dict[str, Any]:
    return _look(data).get("tonight") or {}


def _spray(data: dict[str, Any]) -> dict[str, Any]:
    return _look(data).get("spray") or {}


def _check(data: dict[str, Any]) -> dict[str, Any]:
    return _look(data).get("station_check") or {}


def _derived(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("derived") or {}


def _spray_window_text(data: dict[str, Any]) -> str | None:
    spray = _spray(data)
    if not spray:
        return None
    window = spray.get("window")
    if window:
        return f"{window.get('from')}–{window.get('to')}"
    return "none"


def _last_upload(data: dict[str, Any]) -> datetime | None:
    push = (data.get("station") or {}).get("push") or {}
    raw = push.get("last_push_at")
    return dt_util.parse_datetime(raw) if raw else None


SENSORS: tuple[NuaSenseSensorDescription, ...] = (
    NuaSenseSensorDescription(
        key="tonight_low",
        name="Tonight's low",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value=lambda d: _tonight(d).get("low_c"),
        attributes=lambda d: {"at": _tonight(d).get("at"), "grass_level_c": _tonight(d).get("grass_low_c")},
    ),
    NuaSenseSensorDescription(
        key="tonight_frost",
        name="Frost tonight",
        icon="mdi:snowflake-thermometer",
        value=lambda d: _tonight(d).get("frost"),
    ),
    NuaSenseSensorDescription(
        key="spray_window",
        name="Next spray window",
        icon="mdi:spray",
        value=_spray_window_text,
        attributes=lambda d: {
            "date": _spray(d).get("date"),
            "wind_max_ms": _spray(d).get("wind_max_ms"),
            "reason": _spray(d).get("reason"),
        },
    ),
    NuaSenseSensorDescription(
        key="station_check",
        name="Station check",
        icon="mdi:check-decagram-outline",
        value=lambda d: _check(d).get("verdict"),
        attributes=lambda d: {
            "reading_c": _check(d).get("reading_c"),
            "model_c": _check(d).get("model_c"),
            "difference_c": _check(d).get("diff_c"),
        },
    ),
    NuaSenseSensorDescription(
        key="et0_hour",
        name="ET0 last hour",
        native_unit_of_measurement="mm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-outline",
        value=lambda d: _derived(d).get("et0_hour"),
    ),
    NuaSenseSensorDescription(
        key="leaf_wetness_hours",
        name="Leaf wetness, consecutive hours",
        native_unit_of_measurement="h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:leaf",
        value=lambda d: _derived(d).get("lwd_consecutive_hours"),
        attributes=lambda d: {"reason": _derived(d).get("lwd_reason")},
    ),
    NuaSenseSensorDescription(
        key="spray_quality",
        name="Spray quality",
        icon="mdi:weather-windy",
        value=lambda d: _derived(d).get("spray_quality_label"),
        attributes=lambda d: {
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
        value=lambda d: _derived(d).get("vpd"),
    ),
    NuaSenseSensorDescription(
        key="delta_t",
        name="Delta T",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        value=lambda d: _derived(d).get("delta_t"),
    ),
    NuaSenseSensorDescription(
        key="temperature",
        name="Temperature, hourly mean",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: _derived(d).get("temperature"),
    ),
    NuaSenseSensorDescription(
        key="humidity",
        name="Humidity, hourly mean",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: _derived(d).get("humidity"),
    ),
    NuaSenseSensorDescription(
        key="pressure",
        name="Pressure, hourly mean",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: _derived(d).get("pressure"),
    ),
    NuaSenseSensorDescription(
        key="last_upload",
        name="Last upload",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=_last_upload,
        attributes=lambda d: {"device": ((d.get("station") or {}).get("push") or {}).get("device")},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: NuaSenseCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(NuaSenseSensor(coordinator, entry, description) for description in SENSORS)


class NuaSenseSensor(CoordinatorEntity[NuaSenseCoordinator], SensorEntity):
    """One value NuaSense computes for the station."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    entity_description: NuaSenseSensorDescription

    def __init__(
        self, coordinator: NuaSenseCoordinator, entry: ConfigEntry, description: NuaSenseSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.station_id}_{description.key}"
        station = coordinator.data.get("station") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.station_id)},
            name=entry.title,
            manufacturer="NuaSense",
            model="External station",
            configuration_url="https://platform.nuasense.com/stations",
            suggested_area=None,
            sw_version=None,
            hw_version=(station.get("push") or {}).get("device"),
        )

    @property
    def native_value(self) -> Any:
        try:
            return self.entity_description.value(self.coordinator.data)
        except (TypeError, ValueError, AttributeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        try:
            attrs = self.entity_description.attributes(self.coordinator.data)
        except (TypeError, ValueError, AttributeError):
            return None
        return {k: v for k, v in attrs.items() if v is not None}
