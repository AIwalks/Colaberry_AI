"""Unit tests for the Twilio inbound webhook route (Sprint 11).

POST /twilio/inbound

Tests:
  - happy path: known phone → user_id resolved, EngagementEvent created, TwiML returned
  - missing From → 422
  - missing MessageSid → 422
  - invalid Twilio signature → 403
  - anonymous phone (not in TriggerData) → user_id=None, event still created
  - XML response has correct content-type and body
"""

from __future__ import annotations

import os

# Must be set before app import — lifespan guard requires API_KEY.
os.environ.setdefault("API_KEY", "test-twilio-webhook-key")

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from api.routes.twilio import _get_db_optional
from config.twilio_auth import validate_twilio_signature

# ---------------------------------------------------------------------------
# Patch paths
# ---------------------------------------------------------------------------

_SVC_PATCH   = "api.routes.twilio.EngagementTrackerService"
_MSSQL_PATCH = "api.routes.twilio.MSSQL_CONFIGURED"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_URL = "/twilio/inbound"

_FORM = {
    "From":       "whatsapp:+15005550006",
    "Body":       "Yes I received it",
    "MessageSid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
}

# ---------------------------------------------------------------------------
# Test client
# ---------------------------------------------------------------------------

client = TestClient(app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Auth bypass fixture — autouse for every test; auth test removes it inline
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _bypass_twilio_auth():
    app.dependency_overrides[validate_twilio_signature] = lambda: None
    yield
    app.dependency_overrides.pop(validate_twilio_signature, None)


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_with_phone():
    """_get_db_optional returns a session where the phone resolves to UserID=42."""
    mock_session = MagicMock()
    mock_trigger = MagicMock()
    mock_trigger.UserID = 42
    mock_session.query.return_value.filter.return_value.first.return_value = mock_trigger
    app.dependency_overrides[_get_db_optional] = lambda: mock_session
    yield mock_session
    app.dependency_overrides.pop(_get_db_optional, None)


@pytest.fixture()
def db_phone_not_found():
    """_get_db_optional returns a session where the phone is not in TriggerData."""
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[_get_db_optional] = lambda: mock_session
    yield mock_session
    app.dependency_overrides.pop(_get_db_optional, None)


@pytest.fixture()
def db_none():
    """_get_db_optional returns None (MSSQL not configured)."""
    app.dependency_overrides[_get_db_optional] = lambda: None
    yield
    app.dependency_overrides.pop(_get_db_optional, None)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_returns_200(db_with_phone):
    with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
        mock_svc.return_value.log_event.return_value = 99
        resp = client.post(_URL, data=_FORM)
    assert resp.status_code == 200


def test_xml_response_content_type(db_with_phone):
    with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
        mock_svc.return_value.log_event.return_value = 99
        resp = client.post(_URL, data=_FORM)
    assert "text/xml" in resp.headers["content-type"]
    assert resp.text.startswith("<?xml")
    assert "<Response/>" in resp.text


def test_happy_path_log_event_called_with_resolved_user_id(db_with_phone):
    with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
        mock_svc.return_value.log_event.return_value = 99
        client.post(_URL, data=_FORM)
    mock_svc.return_value.log_event.assert_called_once_with(
        user_id=42,
        event_type="incoming_message",
        channel="whatsapp",
        message="Yes I received it",
        agent_name="TwilioWebhook",
        thread_id="SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )


# ---------------------------------------------------------------------------
# Form field validation
# ---------------------------------------------------------------------------

def test_missing_from_returns_422(db_none):
    resp = client.post(_URL, data={"Body": "hi", "MessageSid": "SMabc"})
    assert resp.status_code == 422


def test_missing_message_sid_returns_422(db_none):
    resp = client.post(_URL, data={"From": "whatsapp:+15005550006", "Body": "hi"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Twilio signature validation
# ---------------------------------------------------------------------------

def test_invalid_signature_returns_403(monkeypatch):
    # Remove auth bypass so the real validate_twilio_signature runs.
    app.dependency_overrides.pop(validate_twilio_signature, None)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "real_test_token_xyz")
    try:
        resp = client.post(
            _URL,
            data=_FORM,
            headers={"X-Twilio-Signature": "bm90YXZhbGlkc2lnbmF0dXJl"},
        )
        assert resp.status_code == 403
    finally:
        # Restore so the autouse teardown has nothing to clean up.
        app.dependency_overrides[validate_twilio_signature] = lambda: None


# ---------------------------------------------------------------------------
# Anonymous phone (not found in TriggerData)
# ---------------------------------------------------------------------------

def test_anonymous_phone_still_creates_event(db_phone_not_found):
    with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
        mock_svc.return_value.log_event.return_value = 77
        resp = client.post(_URL, data=_FORM)
    assert resp.status_code == 200
    mock_svc.return_value.log_event.assert_called_once()
    kwargs = mock_svc.return_value.log_event.call_args.kwargs
    assert kwargs["user_id"] is None
    assert kwargs["event_type"] == "incoming_message"
    assert kwargs["thread_id"] == "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    assert kwargs["channel"] == "whatsapp"
