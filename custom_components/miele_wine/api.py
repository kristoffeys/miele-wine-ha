"""Async client for Miele's consumer domestic cloud (the app's API).

Not the 3rd-party developer API — this speaks the same endpoints the Miele phone app
uses (rest-*.domestic.miele-iot.com), authenticated with the consumer MAP OAuth token
(scope `mcs`). Reverse-engineered; see the repo's FINDINGS.md.

The client is Home-Assistant-agnostic: it holds a token dict, refreshes when near
expiry, and invokes an optional async `on_tokens` callback so the caller can persist
the rotated tokens (HA stores them in the config entry).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

import aiohttp

REST_HOST_BY_REGION = {
    "EU": "rest-eu.domestic.miele-iot.com",
    "AS": "rest-as.domestic.miele-iot.com",
    "EU2": "rest-eu2.domestic.miele-iot.com",
}
TOKEN_URL = "https://prod.map.miele-iot.com/{cc}/token"
ACCEPT = "application/vnd.miele.v1+json"
UA = "Miele@mobile 4.17.3 Android"
EXPIRY_SKEW = 120
UNUSED_TEMP = -32768

# PresentationLight / zone light values.
LIGHT_ON = 1
LIGHT_OFF = 2


class MieleAuthError(Exception):
    """Token refresh / auth failed — the config entry needs re-authentication."""


class MieleApiError(Exception):
    """A non-auth API error (bad status, network, or a rejected write)."""


def check_write_result(result: Any) -> Any:
    """Raise if a /Cooling write was rejected.

    Writes return HTTP 200 with a body like [{"Success":{"Value":N}}] or
    [{"Failure":{"<field>":null}}]. A Failure means the appliance refused the value
    (out of range, not permitted), so surface it instead of silently succeeding.
    """
    items = result if isinstance(result, list) else [result] if result else []
    failures = [next(iter(i)) for i in items if isinstance(i, dict) and "Failure" in i]
    if failures:
        raise MieleApiError(f"appliance rejected write: {failures}")
    return result


class MieleCloud:
    """Minimal async client for the endpoints this integration needs."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        tokens: dict[str, Any],
        on_tokens: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._session = session
        self._tokens = dict(tokens)
        self._on_tokens = on_tokens

    # --- auth ------------------------------------------------------------
    @property
    def region(self) -> str:
        return self._tokens.get("region", "EU")

    def _host(self) -> str:
        return REST_HOST_BY_REGION.get(self.region, REST_HOST_BY_REGION["EU"])

    async def _access_token(self) -> str:
        t = self._tokens
        expires_in = int(t.get("expires_in", 3600))
        age = int(time.time()) - int(t.get("obtained_at", 0))
        if age < expires_in - EXPIRY_SKEW and t.get("access_token"):
            return t["access_token"]
        if not t.get("refresh_token"):
            raise MieleAuthError("no refresh_token; re-authentication required")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": t["refresh_token"],
            "client_id": t["client_id"],
        }
        url = TOKEN_URL.format(cc=t["cc"])
        try:
            async with self._session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=20)) as r:
                body = await r.json(content_type=None)
        except aiohttp.ClientError as e:
            raise MieleApiError(f"token refresh network error: {e}") from e
        if "access_token" not in body:
            raise MieleAuthError(f"token refresh failed: {body}")
        body.setdefault("refresh_token", t["refresh_token"])
        self._tokens.update(body)
        self._tokens["obtained_at"] = int(time.time())
        if self._on_tokens:
            await self._on_tokens(dict(self._tokens))
        return self._tokens["access_token"]

    async def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._access_token()}",
            "Accept": ACCEPT,
            "Content-Type": "application/json",
            "Accept-Language": "en-GB",
            "User-Agent": UA,
        }

    # --- requests (retry the flaky upstream 500 once) --------------------
    async def _get(self, path: str) -> Any:
        url = f"https://{self._host()}{path}"
        headers = await self._headers()
        last = None
        for attempt in range(3):
            if attempt:
                # small backoff before retrying the flaky upstream 500 (0.5s, 1s)
                await asyncio.sleep(0.5 * attempt)
            try:
                async with self._session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 500:
                        last = 500
                        continue
                    if r.status in (401, 403):
                        raise MieleAuthError(f"{r.status} on GET {path}")
                    if r.status != 200:
                        raise MieleApiError(f"{r.status} on GET {path}")
                    return await r.json(content_type=None)
            except aiohttp.ClientError as e:
                raise MieleApiError(f"network error on GET {path}: {e}") from e
        raise MieleApiError(f"GET {path} kept returning {last}")

    async def _put(self, path: str, body: dict[str, Any]) -> Any:
        url = f"https://{self._host()}{path}"
        headers = await self._headers()
        try:
            async with self._session.put(url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status in (401, 403):
                    raise MieleAuthError(f"{r.status} on PUT {path}")
                if r.status not in (200, 204):
                    raise MieleApiError(f"{r.status} on PUT {path}: {await r.text()}")
                if r.status == 204:
                    return None
                return check_write_result(await r.json(content_type=None))
        except aiohttp.ClientError as e:
            raise MieleApiError(f"network error on PUT {path}: {e}") from e

    # --- endpoints -------------------------------------------------------
    async def discover_mac(self) -> str:
        for gw in await self._get("/V2/Devices/"):
            for dev in gw.get("devices", []):
                if dev.get("mac"):
                    return dev["mac"]
        raise MieleApiError("no device found under /V2/Devices/")

    async def get_cooling(self, mac: str) -> dict[str, Any]:
        return await self._get(f"/V2/Devices/{mac}/Cooling/")

    async def get_zone(self, mac: str, zone: str) -> dict[str, Any]:
        return await self._get(f"/V2/Devices/{mac}/Cooling/{zone}/")

    async def get_ident(self, mac: str) -> dict[str, Any]:
        return await self._get(f"/V2/Devices/{mac}/Ident/")

    async def set_presentation_light(self, mac: str, on: bool) -> None:
        await self._put(
            f"/V2/Devices/{mac}/Cooling/PresentationLight",
            {"Value": LIGHT_ON if on else LIGHT_OFF},
        )

    async def set_cooling_value(self, mac: str, name: str, value: int) -> Any:
        """Generic /Cooling/{name} setter (PresentationLight, Sabbath, AirFilter,
        HumidityControl, ...). Returns e.g. [{"Success":{"Value":N}}]."""
        return await self._put(f"/V2/Devices/{mac}/Cooling/{name}", {"Value": value})

    async def set_zone_value(self, mac: str, zone: str, name: str, value: int) -> Any:
        """Generic /Cooling/{zone}/{name} setter (TargetTemp, PresentationLightIntensity)."""
        return await self._put(f"/V2/Devices/{mac}/Cooling/{zone}/{name}", {"Value": value})
