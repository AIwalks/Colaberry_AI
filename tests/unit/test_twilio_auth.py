"""Unit tests for Twilio webhook signature validation (config/twilio_auth.py).

Tests cover:
  - compute_signature pure function (known-vector and edge cases)
  - valid signature accepted (200)
  - invalid signature rejected (403)
  - missing TWILIO_AUTH_TOKEN returns 503
  - missing X-Twilio-Signature header rejected (403)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from config.twilio_auth import compute_signature, validate_twilio_signature

# ---------------------------------------------------------------------------
# Minimal test app — single POST route protected by the dependency
# ---------------------------------------------------------------------------

_test_app = FastAPI()


@_test_app.post(
    "/test/inbound",
    dependencies=[Depends(validate_twilio_signature)],
)
async def _test_route() -> dict:
    return {"ok": True}


client = TestClient(_test_app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------

_TEST_TOKEN = "test_auth_token_abc123"
_TEST_URL = "http://testserver/test/inbound"
_FORM_PARAMS: dict[str, str] = {
    "From": "whatsapp:+15005550006",
    "Body": "Hello there",
    "MessageSid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
}


def _sign(token: str, params: dict[str, str]) -> str:
    return compute_signature(token, _TEST_URL, params)


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


def test_compute_signature_matches_manual_calculation() -> None:
    """compute_signature must produce the same result as a manual HMAC-SHA1 computation."""
    token = "test_token_12345"
    url = "https://example.com/twilio/inbound"
    params = {"From": "whatsapp:+15005550006", "Body": "hi", "MessageSid": "SMabc"}

    payload = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
    expected = base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()

    assert compute_signature(token, url, params) == expected


def test_compute_signature_sorts_params_alphabetically() -> None:
    """Param order in the input dict must not affect the signature."""
    token = "token"
    url = "https://example.com/"
    params_a = {"Z": "last", "A": "first", "M": "middle"}
    params_b = {"M": "middle", "Z": "last", "A": "first"}
    assert compute_signature(token, url, params_a) == compute_signature(token, url, params_b)


def test_compute_signature_empty_params() -> None:
    """Empty param dict should produce a valid (non-empty) base64 string."""
    sig = compute_signature("token", "https://example.com/", {})
    assert isinstance(sig, str)
    assert len(sig) > 0


def test_compute_signature_different_tokens_produce_different_signatures() -> None:
    sig_a = compute_signature("token_a", "https://example.com/", {"k": "v"})
    sig_b = compute_signature("token_b", "https://example.com/", {"k": "v"})
    assert sig_a != sig_b


# ---------------------------------------------------------------------------
# Dependency integration tests
# ---------------------------------------------------------------------------


def test_valid_signature_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", _TEST_TOKEN)
    sig = _sign(_TEST_TOKEN, _FORM_PARAMS)
    resp = client.post(
        "/test/inbound",
        data=_FORM_PARAMS,
        headers={"X-Twilio-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_invalid_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", _TEST_TOKEN)
    resp = client.post(
        "/test/inbound",
        data=_FORM_PARAMS,
        headers={"X-Twilio-Signature": "bm90YXZhbGlkc2lnbmF0dXJl"},
    )
    assert resp.status_code == 403
    assert "Invalid" in resp.json()["detail"]


def test_missing_token_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    sig = _sign("irrelevant", _FORM_PARAMS)
    resp = client.post(
        "/test/inbound",
        data=_FORM_PARAMS,
        headers={"X-Twilio-Signature": sig},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


def test_missing_signature_header_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """No X-Twilio-Signature header — FastAPI defaults to empty string, must 403."""
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", _TEST_TOKEN)
    resp = client.post("/test/inbound", data=_FORM_PARAMS)
    assert resp.status_code == 403


def test_tampered_body_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Signature computed over original params must not validate altered params."""
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", _TEST_TOKEN)
    sig = _sign(_TEST_TOKEN, _FORM_PARAMS)
    tampered = {**_FORM_PARAMS, "Body": "injected content"}
    resp = client.post(
        "/test/inbound",
        data=tampered,
        headers={"X-Twilio-Signature": sig},
    )
    assert resp.status_code == 403
