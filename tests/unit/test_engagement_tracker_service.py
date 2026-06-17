"""Tests for EngagementTrackerService.

Unit tests (no DB) run unconditionally and verify the RuntimeError guard.
Integration tests skip cleanly when MSSQL_DATABASE_URL is not configured,
following the project's existing DB-test pattern.
"""

import os

import pytest

_DB_URL = os.environ.get("MSSQL_DATABASE_URL")

# ---------------------------------------------------------------------------
# Unit tests — no DB required
# ---------------------------------------------------------------------------

def test_raises_runtime_error_when_session_local_is_none(monkeypatch):
    """Service must raise RuntimeError immediately if SessionLocal is None."""
    import services.engagement_tracker_service as module

    monkeypatch.setattr(module, "SessionLocal", None)

    from services.engagement_tracker_service import EngagementTrackerService

    svc = EngagementTrackerService()
    with pytest.raises(RuntimeError, match="MSSQL_DATABASE_URL"):
        svc.log_event(
            user_id    = 1,
            event_type = "test_event",
            channel    = "whatsapp",
            message    = "hello",
            agent_name = "TestAgent",
            trigger_id = None,
        )


def test_thread_id_is_stored_when_supplied(monkeypatch):
    """thread_id supplied → EngagementEvent created with that thread_id value."""
    from unittest.mock import MagicMock
    import services.engagement_tracker_service as module

    captured = {}

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.add.side_effect = lambda obj: captured.update({"event": obj})
    mock_session.refresh.side_effect = lambda obj: setattr(obj, "id", 1)

    monkeypatch.setattr(module, "SessionLocal", MagicMock(return_value=mock_session))

    from services.engagement_tracker_service import EngagementTrackerService

    EngagementTrackerService().log_event(
        user_id    = None,
        event_type = "incoming_message",
        channel    = "whatsapp",
        message    = "test",
        agent_name = "TestAgent",
        thread_id  = "thread-abc-123",
    )

    assert captured["event"].thread_id == "thread-abc-123"


def test_thread_id_defaults_to_none_when_omitted(monkeypatch):
    """thread_id omitted → EngagementEvent created with thread_id=None."""
    from unittest.mock import MagicMock
    import services.engagement_tracker_service as module

    captured = {}

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.add.side_effect = lambda obj: captured.update({"event": obj})
    mock_session.refresh.side_effect = lambda obj: setattr(obj, "id", 2)

    monkeypatch.setattr(module, "SessionLocal", MagicMock(return_value=mock_session))

    from services.engagement_tracker_service import EngagementTrackerService

    EngagementTrackerService().log_event(
        user_id    = None,
        event_type = "incoming_message",
        channel    = "sms",
        message    = "test",
        agent_name = "TestAgent",
    )

    assert captured["event"].thread_id is None


# ---------------------------------------------------------------------------
# Integration tests — skipped when DB is not configured
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _DB_URL, reason="MSSQL_DATABASE_URL not set")
def test_log_event_returns_integer_id():
    """log_event() must return a positive integer PK after a successful insert."""
    from services.engagement_tracker_service import EngagementTrackerService
    from config.database import SessionLocal
    from services.models import EngagementEvent
    from sqlalchemy import select

    svc = EngagementTrackerService()
    returned_id = svc.log_event(
        user_id    = None,
        event_type = "test_event",
        channel    = "whatsapp",
        message    = "integration test message",
        agent_name = "TestAgent",
        trigger_id = None,
    )

    assert isinstance(returned_id, int), f"Expected int, got {type(returned_id)}"
    assert returned_id > 0, f"Expected positive PK, got {returned_id}"

    # Clean up the test row
    with SessionLocal() as session:
        row = session.get(EngagementEvent, returned_id)
        if row is not None:
            session.delete(row)
            session.commit()


@pytest.mark.skipif(not _DB_URL, reason="MSSQL_DATABASE_URL not set")
def test_log_event_writes_correct_fields():
    """Row written to AI_ChatBot_EngagementEvents must match the supplied values."""
    from services.engagement_tracker_service import EngagementTrackerService
    from config.database import SessionLocal
    from services.models import EngagementEvent

    svc = EngagementTrackerService()
    returned_id = svc.log_event(
        user_id    = 42,
        event_type = "nudge_sent",
        channel    = "sms",
        message    = "Your session starts tomorrow.",
        agent_name = "MentorAgent",
        trigger_id = 99,
    )

    row: EngagementEvent | None = None
    with SessionLocal() as session:
        try:
            row = session.get(EngagementEvent, returned_id)

            assert row is not None,        "Row not found after insert"
            assert row.user_id    == 42,                    f"user_id mismatch: {row.user_id}"
            assert row.event_type == "nudge_sent",          f"event_type mismatch: {row.event_type}"
            assert row.channel    == "sms",                 f"channel mismatch: {row.channel}"
            assert row.message    == "Your session starts tomorrow.", f"message mismatch"
            assert row.agent_name == "MentorAgent",         f"agent_name mismatch: {row.agent_name}"
            assert row.trigger_id == 99,                    f"trigger_id mismatch: {row.trigger_id}"
            assert row.created_at is not None,              "created_at must not be None"

        finally:
            if row is not None:
                session.delete(row)
                session.commit()
