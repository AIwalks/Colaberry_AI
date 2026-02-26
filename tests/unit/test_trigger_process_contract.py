"""Contract test for POST /ai/trigger/process happy path."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_trigger_process_happy_path_returns_expected_shape_and_mapping():
    resp = client.post("/ai/trigger/process", json={
        "trigger_type": "nudge_needed",
        "student_id": "S1",
        "event_id": "E1",
        "timestamp": "2026-02-10T00:00:00Z",
        "metadata": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"event_id", "accepted", "actions_planned", "notes"}
    assert data["event_id"] == "E1"
    assert data["accepted"] is True
    assert data["actions_planned"] == ["queue_nudge_message"]
    assert isinstance(data["notes"], str) and len(data["notes"]) > 0
