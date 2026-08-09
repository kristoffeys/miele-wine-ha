"""Unit tests for the OAuth/PKCE helpers (no network, no Home Assistant)."""
import base64
import hashlib
import urllib.parse

import pytest

import auth


def _b64url_sha256(v: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()


def test_build_authorize_url_pkce_s256():
    url, challenge = auth.build_authorize_url("be")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["code_challenge_method"] == ["S256"]
    assert q["client_id"][0] == challenge["client_id"]
    # the challenge is the S256 hash of the stored verifier
    assert q["code_challenge"][0] == _b64url_sha256(challenge["verifier"])
    assert q["state"][0] == challenge["state"]
    assert challenge["cc"] == "be"


def test_parse_redirect_ok():
    code = auth.parse_redirect("miele://oauth2-code/?code=ABC123&state=xyz", "xyz")
    assert code == "ABC123"


def test_parse_redirect_state_mismatch():
    with pytest.raises(ValueError):
        auth.parse_redirect("miele://oauth2-code/?code=ABC&state=wrong", "expected")


def test_parse_redirect_error_param():
    with pytest.raises(ValueError):
        auth.parse_redirect("miele://oauth2-code/?error=access_denied", "s")


def test_parse_redirect_no_code():
    with pytest.raises(ValueError):
        auth.parse_redirect("miele://oauth2-code/?state=s", "s")


def test_region_and_client_id():
    assert auth.region_for("us") == "EU2"
    assert auth.region_for("be") == "EU"
    assert auth.client_id_for("be") == auth.client_id_for("de")  # BE reuses DE's id
    assert auth.client_id_for("zz") == auth.client_id_for("de")  # unknown -> de fallback
