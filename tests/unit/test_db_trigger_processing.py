"""Integration test — DB-backed trigger processing endpoint.

Skipped automatically when MSSQL_DATABASE_URL is not configured.
To run against a live database:

    MSSQL_DATABASE_URL="mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server"  # pragma: allowlist secret \
        pytest tests/unit/test_db_trigger_processing.py -v

What this test does
-------------------
1. POSTs to /ai/trigger/process with a deterministic payload.
2. Asserts the response contains the four required keys.
3. If the trigger was accepted (rule found in DB), verifies that a
   matching row was written to AI_ChatBot_TriggeredUsers, then deletes
   that row so the test leaves no permanent data behind.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

_DB_URL = os.environ.get("MSSQL_DATABASE_URL")

# ---------------------------------------------------------------------------
# Deterministic payload — student_id "1" may or may not exist in TriggerData;
# DbTriggerProcessingService handles a missing student gracefully (level=Unknown).
# ---------------------------------------------------------------------------
_PAYLOAD = {
    "trigger_type": "nudge_needed",
    "student_id":   "1",
    "event_id":     "TEST-EVT-DB-001",
    "timestamp":    "2026-03-09T00:00:00Z",
}


@pytest.mark.skipif(not _DB_URL, reason="MSSQL_DATABASE_URL not set")
def test_db_trigger_process_returns_correct_shape():
    """Response always contains the four required top-level keys."""
    from app.main import app

    client = TestClient(app, headers={"X-Api-Key": "test-key"})
    response = client.post("/ai/trigger/process", json=_PAYLOAD)

    assert response.status_code == 200
    data = response.json()

    assert "event_id"        in data
    assert "accepted"        in data
    assert "actions_planned" in data
    assert "notes"           in data
    assert data["event_id"] == _PAYLOAD["event_id"]
    assert isinstance(data["accepted"], bool)
    assert isinstance(data["actions_planned"], list)
    assert isinstance(data["notes"], str) and len(data["notes"]) > 0


@pytest.mark.skipif(not _DB_URL, reason="MSSQL_DATABASE_URL not set")
def test_db_trigger_process_writes_triggered_user_row_when_accepted():
    """When accepted=True, a matching TriggeredUser row must exist in the DB.

    The inserted row is deleted at the end of the test so the database is
    left in the same state it was before the test ran.
    """
    from app.main import app
    from config.database import SessionLocal
    from services.models import TriggeredUser

    client = TestClient(app, headers={"X-Api-Key": "test-key"})
    response = client.post("/ai/trigger/process", json=_PAYLOAD)

    assert response.status_code == 200
    data = response.json()

    if not data["accepted"]:
        pytest.skip(
            f"trigger_type={_PAYLOAD['trigger_type']!r} not found in TriggerRules — "
            "skipping row-verification portion"
        )

    row: TriggeredUser | None = None
    with SessionLocal() as session:
        try:
            row = session.execute(
                select(TriggeredUser)
                .where(TriggeredUser.TriggerType == _PAYLOAD["trigger_type"])
                .order_by(TriggeredUser.CBM_ID.desc())
            ).scalars().first()

            assert row is not None, (
                "Expected a TriggeredUser row to be written to "
                "AI_ChatBot_TriggeredUsers after a successful trigger"
            )
            assert row.TriggerType  == _PAYLOAD["trigger_type"]
            assert row.TriggerLevel in ("Low", "High", "None", "Unknown")
            assert row.Completed    == 0
            assert row.InsertDate   is not None

        finally:
            # Clean up: remove the test row regardless of assertion outcome
            if row is not None:
                session.delete(row)
                session.commit()
