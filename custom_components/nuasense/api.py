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

    async def _get(self, path: str) -> Any:
        headers = {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}
        try:
            async with self._session.get(
                f"{self._base}{path}", headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as res:
                if res.status in (401, 403):
                    raise NuaSenseAuthError("NuaSense did not accept the API key")
                body = await res.json(content_type=None)
                if res.status == 409:
                    raise NuaSenseNoPositionError(body.get("error") or "no position")
                if res.status >= 400:
                    raise NuaSenseError(body.get("error") or body.get("message") or f"HTTP {res.status}")
                return body
        except aiohttp.ClientError as err:
            raise NuaSenseError(f"NuaSense could not be reached: {err}") from err

    async def stations(self) -> list[dict[str, Any]]:
        body = await self._get("/api/nuasense/v1/ingest/stations")
        return list(body.get("stations") or [])

    async def first_look(self, station_id: str) -> dict[str, Any]:
        return await self._get(f"/api/nuasense/v1/ingest/first-look?station_id={station_id}")

    async def latest_derived(self, station_id: str) -> dict[str, Any] | None:
        body = await self._get(
            f"/api/nuasense/v1/ingest/derived?station_id={station_id}&start=-6h&limit=1"
        )
        rows = body.get("data") or []
        return rows[0] if rows else None
