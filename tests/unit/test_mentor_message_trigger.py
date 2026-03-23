"""Unit tests for MentorMessageService.process_trigger().

DB-dependent tests skip when MSSQL_DATABASE_URL is not set.
The no_db guard test runs unconditionally.
"""

import os
from datetime import datetime

import pytest

_DB_URL = os.environ.get("MSSQL_DATABASE_URL")


def test_process_trigger_returns_no_db_when_session_not_configured(monkeypatch):
    """process_trigger() must return sent=False/reason=no_db when SessionLocal is None."""
    import services.mentor_message_service as module

    monkeypatch.setattr(module, "SessionLocal", None)

    from services.mentor_message_service import MentorMessageService

    result = MentorMessageService().process_trigger(cbm_id=1)

    assert result["sent"]   is False
    assert result["reason"] == "no_db"


@pytest.mark.skipif(not _DB_URL, reason="MSSQL_DATABASE_URL not set")
def test_process_trigger_marks_completed_and_returns_sent():
    """process_trigger() must set Completed=1 and return sent=True."""
    from config.database import SessionLocal
    from services.models import TriggeredUser
    from services.mentor_message_service import MentorMessageService

    # 1. Insert a minimal TriggeredUser row directly
    with SessionLocal() as session:
        fake_row = TriggeredUser(
            CB_ID        = None,
            UserID       = None,
            TriggerType  = "nudge_needed",
            TriggerLevel = "Low",
            KPI          = None,
            Severity     = None,
            InsertDate   = datetime.utcnow(),
            Completed    = 0,
            AgentID      = None,
        )
        session.add(fake_row)
        session.commit()
        session.refresh(fake_row)
        cbm_id = fake_row.CBM_ID

    # 2. Call process_trigger with the inserted row's PK
    result = MentorMessageService().process_trigger(cbm_id)

    # 3 & 4. Verify result and DB state, then clean up
    with SessionLocal() as session:
        row = session.get(TriggeredUser, cbm_id)
        try:
            assert result["sent"]   is True
            assert result["cbm_id"] == cbm_id
            assert row is not None,     "TriggeredUser row should still exist"
            assert row.Completed  == 1, f"Expected Completed=1, got {row.Completed}"
            assert row.CompletedDate is not None, \
                "CompletedDate must be set when Completed=1"
        finally:
            if row is not None:
                session.delete(row)
                session.commit()
