"""Data quality of the station, as NuaSense validates it (no Home Assistant imports).

NuaSense checks every value as it arrives (World Meteorological Organization
limits, stuck sensors, impossible sunshine), compares the station with the
weather model and the nearest official weather station, and with stations
nearby, and grades each sensor A to D once a day with what to fix.
"""

from __future__ import annotations

from typing import Any

SENSOR_WORD = {
    "temperature": "Thermometer",
    "humidity": "Humidity sensor",
    "wind": "Anemometer",
    "pressure": "Barometer",
    "rain": "Rain gauge",
    "clock": "Clock",
}
FIELD_WORD = {
    "temperature": "Temperature",
    "humidity": "Humidity",
    "pressure": "Pressure",
    "wind_speed": "Wind",
    "wind_gusts": "Gusts",
    "wind_direction": "Wind direction",
    "solar": "Sunshine",
    "rain_mm": "Rain",
}
STATES = ["A", "B", "C", "D", "not_graded"]


def quality_of(data: dict[str, Any]) -> dict[str, Any] | None:
    """The quality block from the station listing, else from the first look."""
    station = (data or {}).get("station") or {}
    q = station.get("quality") or ((data or {}).get("first_look") or {}).get("quality")
    return q if isinstance(q, dict) else None


def quality_state(q: dict[str, Any] | None) -> str | None:
    if not q:
        return None
    grade = q.get("grade")
    if grade in ("A", "B", "C", "D"):
        return grade
    return "not_graded" if q.get("not_graded") else None


def quality_attributes(q: dict[str, Any] | None) -> dict[str, Any]:
    """What is wrong and what to do, one line each; where it was checked against."""
    if not q:
        return {}
    problems = []
    for sensor, s in (q.get("sensors") or {}).items():
        if not isinstance(s, dict) or s.get("grade") not in ("C", "D"):
            continue
        issue = next((i for i in s.get("issues") or [] if i.get("severity") != "note"), None)
        if not issue:
            continue
        line = f"{SENSOR_WORD.get(sensor, sensor)} ({s['grade']}): {issue.get('text')}."
        if issue.get("fix"):
            line += f" {issue['fix']}"
        problems.append(line)
    for issue in q.get("station_issues") or []:
        if not isinstance(issue, dict) or issue.get("severity") == "note":
            continue
        line = f"Station: {issue.get('text')}."
        if issue.get("fix"):
            line += f" {issue['fix']}"
        problems.append(line)
    wrong_now = [
        f"{FIELD_WORD.get(field, field)}: {v.get('reason')}"
        for field, v in ((q.get("now") or {}).get("fields") or {}).items()
        if isinstance(v, dict) and v.get("status") in ("stuck", "erroneous")
    ]
    refs = [
        r.get("name") + (f" ({r['distance_km']} km)" if r.get("distance_km") is not None else "")
        for r in q.get("references") or []
        if isinstance(r, dict) and r.get("name")
    ]
    out: dict[str, Any] = {
        "problems": problems,
        "wrong_right_now": wrong_now,
        "checked_against": refs,
        "graded_at": q.get("graded_at"),
    }
    for sensor, s in (q.get("sensors") or {}).items():
        if isinstance(s, dict) and s.get("grade"):
            out[f"grade_{sensor}"] = s["grade"]
    if q.get("not_graded"):
        reason = str(q["not_graded"])
        out["not_graded"] = "graded once the station has three days of readings" if "fewer than" in reason else reason
    return out
