"""Unit tests for the AI Mentor Message contract (happy path + request-id echo)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_BODY = {
    "student_id": "stu-001",
    "channel": "web",
    "message": "Hello mentor",
}

EXPECTED_TOP_KEYS = {
    "request_id",
    "received",
    "student_status",
    "delivery",
    "response_message",
    "engagement_log",
}


def test_contract_happy_path_shape():
    resp = client.post("/ai/mentor/message", json=VALID_BODY)
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == EXPECTED_TOP_KEYS
    assert "lifecycle_stage" in data["student_status"]
    assert "summary" in data["student_status"]


def test_request_id_echoes_header():
    resp = client.post(
        "/ai/mentor/message",
        json=VALID_BODY,
        headers={"X-Request-Id": "test-123"},
    )
    assert resp.status_code == 200
    assert resp.json()["request_id"] == "test-123"
