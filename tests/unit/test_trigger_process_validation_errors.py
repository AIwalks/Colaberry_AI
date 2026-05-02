"""Validation error tests for POST /ai/trigger/process."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-Api-Key": "test-key"})


def valid_payload() -> dict:
    return {
        "trigger_type": "nudge_needed",
        "student_id": "S1",
        "event_id": "E1",
        "timestamp": "2026-02-10T00:00:00Z",
        "metadata": {},
    }


def test_empty_trigger_type_returns_422():
    body = valid_payload()
    body["trigger_type"] = " "
    assert client.post("/ai/trigger/process", json=body).status_code == 422


def test_empty_student_id_returns_422():
    body = valid_payload()
    body["student_id"] = " "
    assert client.post("/ai/trigger/process", json=body).status_code == 422


def test_empty_event_id_returns_422():
    body = valid_payload()
    body["event_id"] = " "
    assert client.post("/ai/trigger/process", json=body).status_code == 422


def test_invalid_trigger_type_type_returns_422():
    body = valid_payload()
    body["trigger_type"] = 123
    assert client.post("/ai/trigger/process", json=body).status_code == 422


def test_missing_trigger_type_returns_422():
    body = valid_payload()
    del body["trigger_type"]
    assert client.post("/ai/trigger/process", json=body).status_code == 422
