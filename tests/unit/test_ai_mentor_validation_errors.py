"""Unit tests for request validation errors on POST /ai/mentor/message."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_BODY = {
    "student_id": "stu-001",
    "channel": "web",
    "message": "Hello",
}


def test_empty_student_id_returns_422():
    resp = client.post("/ai/mentor/message", json={**VALID_BODY, "student_id": " "})
    assert resp.status_code == 422


def test_empty_message_returns_422():
    resp = client.post("/ai/mentor/message", json={**VALID_BODY, "message": " "})
    assert resp.status_code == 422


def test_invalid_channel_returns_422():
    resp = client.post("/ai/mentor/message", json={**VALID_BODY, "channel": "fax"})
    assert resp.status_code == 422
