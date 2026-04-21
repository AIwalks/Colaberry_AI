"""Unit tests for MentorMessageService.process_trigger().

DB-dependent tests skip when MSSQL_DATABASE_URL is not set.
The no_db guard test runs unconditionally.
"""

import os
from datetime import datetime
from unittest.mock import patch

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


# ---------------------------------------------------------------------------
# DeliverySucceeded write-back tests
# All cases use local SQLite — no MSSQL required.
# send_text() is patched so no real network calls are made.
# ---------------------------------------------------------------------------


def _insert_triggered_user() -> int:
    """Insert a minimal TriggeredUser row and return its CBM_ID."""
    from config.database import SessionLocal
    from services.models import TriggeredUser
    with SessionLocal() as session:
        row = TriggeredUser(
            CB_ID=None, UserID=None, TriggerType="test_delivery_succeeded",
            TriggerLevel="Low", KPI=None, Severity=None,
            InsertDate=datetime.utcnow(), Completed=0, AgentID=None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.CBM_ID


def _delete_triggered_user(cbm_id: int) -> None:
    from config.database import SessionLocal
    from services.models import TriggeredUser
    with SessionLocal() as session:
        row = session.get(TriggeredUser, cbm_id)
        if row is not None:
            session.delete(row)
            session.commit()


def _read_delivery_succeeded(cbm_id: int):
    from config.database import SessionLocal
    from services.models import TriggeredUser
    with SessionLocal() as session:
        row = session.get(TriggeredUser, cbm_id)
        return row.DeliverySucceeded if row is not None else "ROW_MISSING"


class TestDeliverySucceededWriteback:
    """Covers all 3 semantic states of DeliverySucceeded written by process_trigger().

    All tests patch MSSQL_CONFIGURED=True so process_trigger() reaches the
    delivery/write-back logic rather than returning early with reason='no_db'.
    Local SQLite is used for all DB operations — no real network calls are made.
    """

    def test_delivery_succeeded_true_when_at_least_one_channel_succeeds(self):
        """Case A: send_text() returns non-empty list with ≥1 success=True.
        DeliverySucceeded must be True on the TriggeredUser row.
        """
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": True,  "channel": "sms",   "provider": "twilio",
                 "provider_id": "SM1", "error": None, "recipient": "+1555"},
                {"success": False, "channel": "email", "provider": "smtp",
                 "provider_id": None, "error": "timeout", "recipient": "a@b.com"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results):
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert _read_delivery_succeeded(cbm_id) is True, \
                "DeliverySucceeded must be True when at least one channel succeeded"
        finally:
            _delete_triggered_user(cbm_id)

    def test_delivery_succeeded_false_when_all_channels_fail(self):
        """Case B: send_text() returns non-empty list where all success=False.
        DeliverySucceeded must be False on the TriggeredUser row.
        """
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": False, "channel": "sms",   "provider": "twilio",
                 "provider_id": None, "error": "auth_error", "recipient": "+1555"},
                {"success": False, "channel": "email", "provider": "smtp",
                 "provider_id": None, "error": "conn_refused", "recipient": "a@b.com"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results):
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert _read_delivery_succeeded(cbm_id) is False, \
                "DeliverySucceeded must be False when all channels failed"
        finally:
            _delete_triggered_user(cbm_id)

    def test_delivery_succeeded_null_when_no_attempt_made(self):
        """Case C: send_text() returns [] (no credentials/no contact info).
        DeliverySucceeded must remain NULL — not False.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=[]):
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert _read_delivery_succeeded(cbm_id) is None, \
                "DeliverySucceeded must be NULL when no delivery was attempted"
        finally:
            _delete_triggered_user(cbm_id)

    def test_delivery_succeeded_false_when_send_text_raises(self):
        """Case D: send_text() raises an exception (unhandled).
        DeliverySucceeded must be False — delivery was attempted and failed.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       side_effect=RuntimeError("unexpected provider crash")):
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("reason") == "delivery_failed", \
                "process_trigger must return reason=delivery_failed on send_text exception"
            assert _read_delivery_succeeded(cbm_id) is False, \
                "DeliverySucceeded must be False when send_text() raises"
        finally:
            _delete_triggered_user(cbm_id)

    def test_retry_preserves_intended_value_not_false_for_empty_results(self):
        """Case E: Primary write-back fails; retry must write delivery_succeeded (None),
        not a hardcoded False, for the empty-results (no-attempt) case.

        Session call order inside process_trigger (with MSSQL_CONFIGURED=True):
          Call 1 — main session block: reads TriggeredUser, commits Completed=1
          Call 2 — write-back primary: must fail to trigger the retry path
          Call 3 — write-back retry: must succeed and write None (not False)

        After the retry, DeliverySucceeded must be None because delivery_results=[].
        """
        cbm_id = _insert_triggered_user()
        try:
            import services.mentor_message_service as svc_module
            original_session_local = svc_module.SessionLocal
            call_count = {"n": 0}

            class _FailOnSecondCall:
                """Passes call 1 (main session) and call 3 (retry); fails call 2 (primary write-back)."""
                def __call__(self):
                    call_count["n"] += 1
                    if call_count["n"] == 2:
                        raise RuntimeError("simulated primary write-back failure")
                    return original_session_local()

            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=[]):   # no-attempt → delivery_succeeded = None
                svc_module.SessionLocal = _FailOnSecondCall()
                try:
                    from services.mentor_message_service import MentorMessageService
                    MentorMessageService().process_trigger(cbm_id)
                finally:
                    svc_module.SessionLocal = original_session_local

            # Retry must have written None (delivery_succeeded), not False
            assert _read_delivery_succeeded(cbm_id) is None, (
                "Retry must write delivery_succeeded=None, not hardcoded False, "
                "for the empty-results no-attempt case"
            )
        finally:
            _delete_triggered_user(cbm_id)
