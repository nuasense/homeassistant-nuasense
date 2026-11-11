"""A thin client for the NuaSense API, scoped to what this integration reads."""

from __future__ import annotations

from typing import Any

import aiohttp


class NuaSenseError(Exception):
    """NuaSense answered with an error."""


class NuaSenseAuthError(NuaSenseError):
    """The API key was refused."""


class NuaSenseNoPositionError(NuaSenseError):
    """The station has no position yet, so there is no first look."""


class NuaSenseApi:
    """Reads an account's external stations and what NuaSense computes for them."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, base_url: str) -> None:
        self._session = session
        self._key = api_key.strip()
        self._base = base_url.rstrip("/")

    async def _get(self, path: str) -> dict[str, Any]:
        """GET a path and return its JSON object.

        Every way the request can fail — a timeout, a connection error, a proxy
        answering with an HTML page, a body that is not a JSON object — becomes
        a NuaSenseError, so callers handle one exception type.
        """
        headers = {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}
        try:
            async with self._session.get(
                f"{self._base}{path}", headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as res:
                if res.status in (401, 403):
                    raise NuaSenseAuthError("NuaSense did not accept the API key")
                decoded = await res.json(content_type=None)
                body: dict[str, Any] = decoded if isinstance(decoded, dict) else {}
                if res.status == 409:
                    raise NuaSenseNoPositionError(str(body.get("error") or "no position"))
                if res.status >= 400:
                    raise NuaSenseError(
                        str(body.get("error") or body.get("message") or f"HTTP {res.status}")
                    )
                if not isinstance(decoded, dict):
                    raise NuaSenseError("NuaSense answered with something that is not a JSON object")
                return body
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise NuaSenseError(f"NuaSense could not be reached: {err}") from err

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON and return the answer's JSON object; every failure becomes a NuaSenseError."""
        headers = {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}
        try:
            async with self._session.post(
                f"{self._base}{path}", json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as res:
                if res.status in (401, 403):
                    raise NuaSenseAuthError("NuaSense did not accept the API key for this")
                decoded = await res.json(content_type=None)
                body: dict[str, Any] = decoded if isinstance(decoded, dict) else {}
                if res.status >= 400:
                    raise NuaSenseError(str(body.get("error") or body.get("message") or f"HTTP {res.status}"))
                return body
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise NuaSenseError(f"NuaSense could not be reached: {err}") from err

    async def create_station(self, station_id: str, name: str, latitude: float | None, longitude: float | None, altitude_m: float | None) -> dict[str, Any]:
        """Register a station on the account (the first three are free)."""
        body = await self._post(
            "/api/nuasense/v1/ingest/stations",
            {"station_id": station_id, "name": name, "latitude": latitude, "longitude": longitude, "altitude_m": altitude_m},
        )
        return body.get("station") if isinstance(body.get("station"), dict) else {}

    async def push_token(self, station_id: str) -> str:
        """A new upload address for the station; any earlier one stops working."""
        body = await self._post(f"/api/nuasense/v1/ingest/stations/{station_id}/push-token", {})
        setup = body.get("setup") if isinstance(body.get("setup"), dict) else {}
        path = setup.get("path")
        if not isinstance(path, str) or not path.startswith("/station/"):
            raise NuaSenseError("NuaSense did not return an upload address")
        return path

    async def send_reading(self, push_path: str, params: dict[str, str]) -> int:
        """One upload in the Weather Underground format, over HTTPS; returns the HTTP status."""
        try:
            async with self._session.get(
                f"{self._base}{push_path}", params=params, timeout=aiohttp.ClientTimeout(total=20)
            ) as res:
                await res.read()
                return res.status
        except (TimeoutError, aiohttp.ClientError) as err:
            raise NuaSenseError(f"upload failed: {err}") from err

    async def stations(self) -> list[dict[str, Any]]:
        body = await self._get("/api/nuasense/v1/ingest/stations")
        stations = body.get("stations")
        return [s for s in stations if isinstance(s, dict)] if isinstance(stations, list) else []

    async def disease_risk(self, station_id: str, crop: str) -> dict[str, Any]:
        """Disease and pest risk for one crop at this station, from its own hours."""
        return await self._get(f"/api/nuasense/v1/ingest/disease-risk?station_id={station_id}&crop={crop}")

    async def first_look(self, station_id: str) -> dict[str, Any]:
        return await self._get(f"/api/nuasense/v1/ingest/first-look?station_id={station_id}")

    async def latest_derived(self, station_id: str) -> dict[str, Any] | None:
        body = await self._get(
            f"/api/nuasense/v1/ingest/derived?station_id={station_id}&start=-6h&limit=1"
        )
        rows = body.get("data")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0]
        return None
