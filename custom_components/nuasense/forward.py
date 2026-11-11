"""Which sensors of a weather station Home Assistant already has go to NuaSense, and how.

Pure functions, no Home Assistant import, so they can be tested on their own.

A station is sent in the Weather Underground upload format that NuaSense's
station receiver already reads from consoles (imperial key names; the receiver
converts by name). Each reading is converted from the unit Home Assistant
reports into the unit its key names: °F, inHg, mph, inches, W/m².
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

# What NuaSense reads, in the order the setup dialog shows it.
ROLES = ["temperature", "humidity", "pressure", "wind_speed", "wind_gust", "wind_direction", "rain", "solar"]


@dataclass(frozen=True)
class Candidate:
    """One sensor entity of the chosen device."""

    entity_id: str
    device_class: str | None
    unit: str | None
    name: str


_INDOOR = re.compile(r"\b(indoor|inside|in-?house|console|base station|room)\b|\bin\b(?= (temp|humid))", re.I)


def _name(c: Candidate) -> str:
    return f"{c.name} {c.entity_id}".lower().replace("_", " ")


def _rank(role: str, c: Candidate) -> int | None:
    """How well a sensor fits a role; None when it does not fit at all. Lower is better."""
    n = _name(c)
    dc = (c.device_class or "").lower()
    unit = (c.unit or "").strip()
    indoor = bool(_INDOOR.search(n))
    if role == "temperature":
        if dc != "temperature" or re.search(r"dew|feels|apparent|chill|heat index|soil|leaf|water|pool|probe|cpu", n):
            return None
        return 2 if indoor else (0 if re.search(r"outdoor|outside|exterior", n) else 1)
    if role == "humidity":
        if dc != "humidity" or re.search(r"soil|leaf", n):
            return None
        return 2 if indoor else (0 if re.search(r"outdoor|outside|exterior", n) else 1)
    if role == "pressure":
        if dc not in ("pressure", "atmospheric_pressure"):
            return None
        return 0 if "absolute" in n else (1 if re.search(r"relative|sea", n) else 2)
    if role == "wind_speed":
        if dc not in ("wind_speed", "speed") or re.search(r"gust|max", n):
            return None
        return 0 if re.search(r"average|avg|mean", n) else 1
    if role == "wind_gust":
        if dc not in ("wind_speed", "speed") or not re.search(r"gust", n):
            return None
        return 0 if not re.search(r"max daily|daily max", n) else 2
    if role == "wind_direction":
        if not re.search(r"direction|bearing|winddir", n) or (unit and unit not in ("°", "deg", "degrees")):
            return None
        return 0 if not re.search(r"gust|average|avg", n) else 1
    if role == "rain":
        if dc not in ("precipitation",) and not (re.search(r"rain", n) and unit in ("mm", "in", "cm")):
            return None
        if rain_key(c) is None:
            return None
        return 0 if re.search(r"daily|today|\bday\b", n) else 1
    if role == "solar":
        if dc != "irradiance" and not re.search(r"solar|radiation|irradiance", n):
            return None
        return 0 if unit in ("W/m²", "W/m2") else None
    return None


def pick(candidates: Iterable[Candidate]) -> dict[str, str]:
    """The best sensor per role, by device class first and by name second."""
    out: dict[str, str] = {}
    pool = list(candidates)
    for role in ROLES:
        ranked = sorted(((r, c.entity_id) for c in pool if (r := _rank(role, c)) is not None), key=lambda t: (t[0], t[1]))
        if ranked:
            out[role] = ranked[0][1]
    return out


def rain_key(c: Candidate) -> str | None:
    """Which running total a rain sensor is. Rates are not totals and are not sent."""
    n = _name(c)
    if re.search(r"rate|intensity|per hour|/h\b|hourly|last hour|1h", n):
        return None
    if re.search(r"daily|today|\bday\b", n):
        return "dailyrainin"
    if re.search(r"weekly|week", n):
        return "weeklyrainin"
    if re.search(r"monthly|month", n):
        return "monthlyrainin"
    if re.search(r"yearly|year|annual", n):
        return "yearlyrainin"
    if re.search(r"total|lifetime|accumulated|cumulative", n):
        return "totalrainin"
    return None


def _f(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def to_fahrenheit(v: float, unit: str) -> float | None:
    u = unit.strip().replace("º", "°")
    if u in ("°F", "F"):
        return v
    if u in ("°C", "C"):
        return v * 9 / 5 + 32
    if u == "K":
        return (v - 273.15) * 9 / 5 + 32
    return None


def to_inhg(v: float, unit: str) -> float | None:
    factor = {"inHg": 1.0, "hPa": 1 / 33.8639, "mbar": 1 / 33.8639, "kPa": 10 / 33.8639, "Pa": 0.01 / 33.8639,
              "mmHg": 1 / 25.4, "psi": 2.03602, "cbar": 1 / 3.38639, "bar": 1000 / 33.8639}.get(unit.strip())
    return None if factor is None else v * factor


def to_mph(v: float, unit: str) -> float | None:
    factor = {"mph": 1.0, "m/s": 2.236936, "km/h": 0.6213712, "kn": 1.150779, "knots": 1.150779, "ft/s": 0.6818182}.get(unit.strip())
    return None if factor is None else v * factor


def to_inches(v: float, unit: str) -> float | None:
    factor = {"in": 1.0, "mm": 1 / 25.4, "cm": 1 / 2.54}.get(unit.strip())
    return None if factor is None else v * factor


def to_query(states: dict[str, tuple[Any, str | None]], mapping: dict[str, str], rain_param: str | None, pressure_param: str) -> dict[str, str]:
    """The upload's parameters from the mapped sensors' current states.

    `states` maps entity_id → (state, unit). A sensor that is unavailable, not a
    number or in a unit we cannot convert is left out of this upload; the rest go.
    """
    def value(role: str) -> tuple[float, str] | None:
        entity = mapping.get(role)
        if not entity or entity not in states:
            return None
        raw, unit = states[entity]
        v = _f(raw)
        return None if v is None else (v, unit or "")

    q: dict[str, str] = {}

    def put(key: str, v: float | None, digits: int) -> None:
        if v is not None:
            q[key] = f"{v:.{digits}f}"

    if (t := value("temperature")):
        put("tempf", to_fahrenheit(*t), 2)
    if (h := value("humidity")) and 0 <= h[0] <= 100:
        put("humidity", h[0], 1)
    if (p := value("pressure")):
        put(pressure_param, to_inhg(*p), 3)
    if (w := value("wind_speed")) and w[0] >= 0:
        put("windspeedmph", to_mph(*w), 2)
    if (g := value("wind_gust")) and g[0] >= 0:
        put("windgustmph", to_mph(*g), 2)
    if (d := value("wind_direction")) and 0 <= d[0] <= 360:
        put("winddir", d[0], 0)
    if rain_param and (r := value("rain")) and r[0] >= 0:
        put(rain_param, to_inches(*r), 3)
    if (s := value("solar")) and s[0] >= 0 and (s[1] or "").strip() in ("W/m²", "W/m2"):
        put("solarradiation", s[0], 1)
    return q


def pressure_param_for(c: Candidate | None) -> str:
    """Station (absolute) pressure goes as baromabsin; anything else as baromin, which the receiver reduces."""
    return "baromabsin" if c is not None and "absolute" in _name(c) else "baromin"
