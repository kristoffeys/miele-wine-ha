"""Consumer MAP OAuth 2.0 + PKCE (the Miele app's login), async.

Produces the token dict the MieleCloud client and the config entry store. Ported from
the repo's miele_auth.py. `mcs` scope is what rest-*.domestic requires.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import urllib.parse
from typing import Any

import aiohttp

REDIRECT_URI = "miele://oauth2-code/"
OAUTH_SCOPE = "openid mcs bpdata zuora"
AUTHORIZE_URL = "https://prod.map.miele-iot.com/{cc}/authorize?{qs}"
TOKEN_URL = "https://prod.map.miele-iot.com/{cc}/token"

# Per-country MAP consumer client ids (from the official app). Belgium is a copy of
# Germany's (verified to work through the token exchange — see FINDINGS.md).
CONSUMER_CLIENT_IDS: dict[str, str] = {
    "at": "wNv9HJ3ZcFKH4bxvz0LExQuw", "be": "UJgKOxacIul2BcPJAzrQE6p0",
    "ch": "V52nWiniHyVotglJKplSXnX8", "cz": "npoAzuJP6okjvJ0NqUq9i5Rv",
    "de": "UJgKOxacIul2BcPJAzrQE6p0", "dk": "xWgykqRQSa9THqOXWfzZbxsH",
    "es": "D0Q4NPBR9dwP2EjX4E0_CtHE", "fr": "SOiiE3R4tSD0VxYYBvB8Pi_J",
    "gb": "WigtLzKGJE1Wg6yeZUECV8-P", "hr": "HD4OUUQYAw_5DtVFSe4-rYzR",
    "hu": "2mm2yscHPGJ4tJCVjd6mp-to", "it": "ARQyaYB0ZxLxJ1SJcjJgctuV",
    "lt": "KzeuROL469pqvGFjSYp2ivQ2", "nl": "7ItTbQXQ1wthDOue9jvBQ7Iz",
    "pl": "jWbgLScpvIuqjUoYvf1jS-Is", "pt": "5ZVD-CuJvpG4YpCO9pQhtrGQ",
    "se": "3Mm7m1gD1eU_sUh8yxmShL6S", "si": "UTyhG21RchpI8FPbNeb1vFg1",
    "sk": "pGeafLwcC1_BCLr8DRTCVxSt", "us": "HpsWh2gzgKqRBduPpkZ4Yui9",
}


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def client_id_for(cc: str) -> str:
    return CONSUMER_CLIENT_IDS.get(cc.lower(), CONSUMER_CLIENT_IDS["de"])


def region_for(cc: str) -> str:
    return "EU2" if cc.lower() == "us" else "EU"


def build_authorize_url(cc: str) -> tuple[str, dict[str, str]]:
    """Return (authorize_url, challenge). Keep the challenge for the code exchange."""
    cc = cc.lower()
    client_id = client_id_for(cc)
    verifier = _b64url(secrets.token_bytes(64))
    state = _b64url(secrets.token_bytes(16))
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": OAUTH_SCOPE,
        "state": state,
        "nonce": _b64url(secrets.token_bytes(16)),
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
    }
    url = AUTHORIZE_URL.format(cc=cc, qs=urllib.parse.urlencode(params))
    return url, {"verifier": verifier, "state": state, "cc": cc, "client_id": client_id}


def parse_redirect(redirect_url: str, expected_state: str) -> str:
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)
    if "error" in qs:
        raise ValueError(qs["error"][0])
    if expected_state and qs.get("state", [None])[0] != expected_state:
        raise ValueError("state_mismatch")
    if not qs.get("code"):
        raise ValueError("no_code")
    return qs["code"][0]


async def async_exchange_code(
    session: aiohttp.ClientSession, challenge: dict[str, str], code: str
) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": challenge["client_id"],
        "redirect_uri": REDIRECT_URI,
        "code_verifier": challenge["verifier"],
    }
    async with session.post(
        TOKEN_URL.format(cc=challenge["cc"]), data=data, timeout=aiohttp.ClientTimeout(total=20)
    ) as r:
        tokens = await r.json(content_type=None)
    if "access_token" not in tokens:
        raise ValueError(f"token_exchange_failed: {tokens.get('error', tokens)}")
    tokens["cc"] = challenge["cc"]
    tokens["client_id"] = challenge["client_id"]
    tokens["region"] = region_for(challenge["cc"])
    tokens["obtained_at"] = int(time.time())
    return tokens
