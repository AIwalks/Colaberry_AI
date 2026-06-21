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


# ---------------------------------------------------------------------------
# Atomic claim tests
# Verify that the OUTPUT INSERTED / RETURNING claim pattern prevents duplicate
# sends when two workers process the same cbm_id.
# All tests use local SQLite — no MSSQL required.
# ---------------------------------------------------------------------------


class TestAtomicClaim:
    """Covers the already_claimed guard introduced by the atomic UPDATE RETURNING."""

    def test_second_sequential_call_returns_already_claimed(self):
        """After process_trigger() claims a row (Completed=1), a subsequent call
        for the same cbm_id must return already_claimed without invoking send_text().

        This simulates the steady-state outcome of two workers racing: only one
        sees a returned row from the RETURNING clause; the other exits here.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=[]) as mock_send:
                from services.mentor_message_service import MentorMessageService
                svc = MentorMessageService()

                first  = svc.process_trigger(cbm_id)
                second = svc.process_trigger(cbm_id)

            assert first.get("cbm_id") == cbm_id, \
                "First call must process and return cbm_id"
            assert second == {"sent": False, "reason": "already_claimed"}, \
                "Second call must return already_claimed — not attempt delivery"
            assert mock_send.call_count == 1, \
                "send_text must be called exactly once across both invocations"
        finally:
            _delete_triggered_user(cbm_id)

    def test_already_claimed_does_not_raise(self):
        """already_claimed path must return a dict cleanly with no exception."""
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=[]):
                from services.mentor_message_service import MentorMessageService
                svc = MentorMessageService()
                svc.process_trigger(cbm_id)        # claim it
                result = svc.process_trigger(cbm_id)  # must not raise

            assert isinstance(result, dict)
            assert result["sent"] is False
            assert result["reason"] == "already_claimed"
        finally:
            _delete_triggered_user(cbm_id)

    def test_already_claimed_leaves_completed_flag_unchanged(self):
        """Row must remain Completed=1 after an already_claimed call — the
        losing worker must not reset the flag or corrupt the row state.
        """
        from config.database import SessionLocal
        from services.models import TriggeredUser

        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=[]):
                from services.mentor_message_service import MentorMessageService
                svc = MentorMessageService()
                svc.process_trigger(cbm_id)   # winner
                svc.process_trigger(cbm_id)   # loser — already_claimed

            with SessionLocal() as session:
                row = session.get(TriggeredUser, cbm_id)
                assert row is not None
                assert row.Completed == 1, \
                    "Completed flag must remain 1 after the already_claimed path executes"
        finally:
            _delete_triggered_user(cbm_id)


# ---------------------------------------------------------------------------
# Outcome enrollment wiring tests
# Verify that InterventionOutcomeService.enroll() is called after
# DeliverySucceeded write-back in both delivery outcomes.
# All tests patch InterventionOutcomeService so no real DB is required.
# ---------------------------------------------------------------------------


class TestOutcomeEnrollmentTriggered:
    """enroll() must be invoked after DeliverySucceeded is written, in both
    the successful-delivery and the exception-delivery paths.  Failure of
    enroll() must be fully absorbed — process_trigger() must still return
    its normal result.
    """

    def test_enroll_called_after_successful_delivery(self):
        """enroll() is called once with delivery_succeeded=True when ≥1 channel
        succeeds and cbm_id matches the processed trigger.
        """
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": True, "channel": "sms", "provider": "twilio",
                 "provider_id": "SM1", "error": None, "recipient": "+1555"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results), \
                 patch("services.mentor_message_service.InterventionOutcomeService") as mock_cls:
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("cbm_id") == cbm_id
            mock_cls.return_value.enroll.assert_called_once()
            kwargs = mock_cls.return_value.enroll.call_args.kwargs
            assert kwargs["cbm_id"] == cbm_id
            assert kwargs["delivery_succeeded"] is True
        finally:
            _delete_triggered_user(cbm_id)

    def test_enroll_called_after_failed_delivery(self):
        """enroll() is called once with delivery_succeeded=False when send_text()
        raises an exception — the exception/failure delivery path.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       side_effect=RuntimeError("network error")), \
                 patch("services.mentor_message_service.InterventionOutcomeService") as mock_cls:
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("reason") == "delivery_failed"
            mock_cls.return_value.enroll.assert_called_once()
            kwargs = mock_cls.return_value.enroll.call_args.kwargs
            assert kwargs["cbm_id"] == cbm_id
            assert kwargs["delivery_succeeded"] is False
        finally:
            _delete_triggered_user(cbm_id)

    def test_enroll_failure_does_not_break_process_trigger(self):
        """If enroll() raises, process_trigger() must still return its
        normal sent=True result — enrollment is a non-fatal side effect.
        """
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": True, "channel": "sms", "provider": "twilio",
                 "provider_id": "SM1", "error": None, "recipient": "+1555"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results), \
                 patch("services.mentor_message_service.InterventionOutcomeService") as mock_cls:
                mock_cls.return_value.enroll.side_effect = RuntimeError("enroll crash")
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("cbm_id") == cbm_id
            assert result.get("sent") is True
        finally:
            _delete_triggered_user(cbm_id)

    def test_enroll_not_called_on_already_claimed(self):
        """The already_claimed path exits before delivery — enroll() must not
        be called for a trigger that was already processed by another worker.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=[]), \
                 patch("services.mentor_message_service.InterventionOutcomeService") as mock_cls:
                from services.mentor_message_service import MentorMessageService
                svc = MentorMessageService()
                svc.process_trigger(cbm_id)   # winner — enroll called once
                svc.process_trigger(cbm_id)   # loser — already_claimed; enroll must not fire again

            assert mock_cls.return_value.enroll.call_count == 1, \
                "enroll() must be called exactly once across both invocations"
        finally:
            _delete_triggered_user(cbm_id)


# ---------------------------------------------------------------------------
# Recommendation tracking wiring tests
# Verify that RecommendationTrackingService.record() is called after
# InterventionOutcomeService.enroll() in both delivery outcomes.
# All tests patch RecommendationTrackingService so no real DB is required.
# ---------------------------------------------------------------------------


class TestRecommendationTrackingTriggered:
    """record() must be invoked after enroll() in both the successful-delivery
    and exception-delivery paths.  Failure of record() must be fully absorbed
    — process_trigger() must still return its normal result.
    """

    def test_tracking_called_after_successful_delivery(self):
        """record() is called once with the correct cbm_id when delivery succeeds."""
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": True, "channel": "sms", "provider": "twilio",
                 "provider_id": "SM1", "error": None, "recipient": "+1555"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results), \
                 patch("services.mentor_message_service.RecommendationTrackingService") as mock_cls:
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("cbm_id") == cbm_id
            mock_cls.return_value.record.assert_called_once()
            kwargs = mock_cls.return_value.record.call_args.kwargs
            assert kwargs["cbm_id"] == cbm_id
        finally:
            _delete_triggered_user(cbm_id)

    def test_tracking_called_after_failed_delivery(self):
        """record() is called once with the correct cbm_id when send_text() raises."""
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       side_effect=RuntimeError("network error")), \
                 patch("services.mentor_message_service.RecommendationTrackingService") as mock_cls:
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("reason") == "delivery_failed"
            mock_cls.return_value.record.assert_called_once()
            kwargs = mock_cls.return_value.record.call_args.kwargs
            assert kwargs["cbm_id"] == cbm_id
        finally:
            _delete_triggered_user(cbm_id)

    def test_tracking_failure_does_not_break_process_trigger(self):
        """If record() raises, process_trigger() must still return its normal
        sent=True result — tracking is a non-fatal side effect.
        """
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": True, "channel": "sms", "provider": "twilio",
                 "provider_id": "SM1", "error": None, "recipient": "+1555"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results), \
                 patch("services.mentor_message_service.RecommendationTrackingService") as mock_cls:
                mock_cls.return_value.record.side_effect = RuntimeError("tracking crash")
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("cbm_id") == cbm_id
            assert result.get("sent") is True
        finally:
            _delete_triggered_user(cbm_id)

    def test_tracking_receives_context_dict(self):
        """recommendation_context kwarg passed to record() must be a dict."""
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": True, "channel": "sms", "provider": "twilio",
                 "provider_id": "SM1", "error": None, "recipient": "+1555"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results), \
                 patch("services.mentor_message_service.RecommendationTrackingService") as mock_cls:
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            kwargs = mock_cls.return_value.record.call_args.kwargs
            assert isinstance(kwargs["recommendation_context"], dict), \
                "recommendation_context must be a dict, not None or a string"
        finally:
            _delete_triggered_user(cbm_id)


# ---------------------------------------------------------------------------
# Adaptive recommendation wiring tests
# Verify that AdaptiveRecommendationService.select_key() is invoked in both
# delivery paths and that its return value reaches
# RecommendationTrackingService.record() as recommendation_key.
# All tests patch AdaptiveRecommendationService so no pool table or MSSQL
# is required.
# ---------------------------------------------------------------------------


class TestAdaptiveRecommendationWiring:
    """select_key() must be invoked on both delivery paths; its return value
    must reach RecommendationTrackingService.record() as recommendation_key.
    Failure of select_key() must be fully absorbed — process_trigger() must
    still return its normal result.

    The test fixture inserts rows with TriggerType="test_delivery_succeeded",
    TriggerLevel="Low", KPI=None, so the expected select_key() kwargs are:
      trigger_type = "test_delivery_succeeded"
      dimension    = "general"          (KPI=None → trigger_kpi or "general")
      risk_level   = "Low"
      fallback_key = "test_delivery_succeeded_low"
                     (f"{trigger_type}_{trigger_level}".lower().replace(" ","_"))
    """

    def test_select_key_called_on_successful_delivery(self):
        """select_key() is called once with the correct trigger context when
        delivery succeeds — the normal happy path.
        """
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": True, "channel": "sms", "provider": "twilio",
                 "provider_id": "SM1", "error": None, "recipient": "+1555"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results), \
                 patch("services.mentor_message_service.AdaptiveRecommendationService") as mock_cls:
                mock_cls.return_value.select_key.return_value = "adapted_key"
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("cbm_id") == cbm_id
            mock_cls.return_value.select_key.assert_called_once()
            kwargs = mock_cls.return_value.select_key.call_args.kwargs
            assert kwargs["trigger_type"] == "test_delivery_succeeded"
            assert kwargs["dimension"]    == "general"
            assert kwargs["risk_level"]   == "Low"
            assert kwargs["fallback_key"] == "test_delivery_succeeded_low"
        finally:
            _delete_triggered_user(cbm_id)

    def test_select_key_called_on_delivery_failed_path(self):
        """select_key() is called once with the correct trigger context when
        send_text() raises — the exception/delivery-failed path.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       side_effect=RuntimeError("network error")), \
                 patch("services.mentor_message_service.AdaptiveRecommendationService") as mock_cls:
                mock_cls.return_value.select_key.return_value = "adapted_key"
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("reason") == "delivery_failed"
            mock_cls.return_value.select_key.assert_called_once()
            kwargs = mock_cls.return_value.select_key.call_args.kwargs
            assert kwargs["trigger_type"] == "test_delivery_succeeded"
        finally:
            _delete_triggered_user(cbm_id)

    def test_select_key_failure_does_not_break_process_trigger(self):
        """If select_key() raises, process_trigger() must still return its
        normal sent=True result — adaptive selection is a non-fatal side effect.
        """
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": True, "channel": "sms", "provider": "twilio",
                 "provider_id": "SM1", "error": None, "recipient": "+1555"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results), \
                 patch("services.mentor_message_service.AdaptiveRecommendationService") as mock_cls:
                mock_cls.return_value.select_key.side_effect = RuntimeError("adaptive crash")
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result.get("cbm_id") == cbm_id
            assert result.get("sent") is True
        finally:
            _delete_triggered_user(cbm_id)

    def test_record_receives_key_from_select_key_not_mechanical_formula(self):
        """recommendation_key passed to record() must be the value returned by
        select_key(), not the mechanical f"{trigger_type}_{trigger_level}" fallback.
        """
        cbm_id = _insert_triggered_user()
        try:
            fake_results = [
                {"success": True, "channel": "sms", "provider": "twilio",
                 "provider_id": "SM1", "error": None, "recipient": "+1555"},
            ]
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=fake_results), \
                 patch("services.mentor_message_service.AdaptiveRecommendationService") as mock_adaptive, \
                 patch("services.mentor_message_service.RecommendationTrackingService") as mock_tracking:
                mock_adaptive.return_value.select_key.return_value = "evidence_driven_key"
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            mock_tracking.return_value.record.assert_called_once()
            kwargs = mock_tracking.return_value.record.call_args.kwargs
            assert kwargs["recommendation_key"] == "evidence_driven_key", \
                "record() must receive the key returned by select_key(), " \
                "not the mechanical fallback formula"
        finally:
            _delete_triggered_user(cbm_id)


# ---------------------------------------------------------------------------
# Governance gate wiring tests
# Verify that GovernanceGateService.check_delivery_approved() is called before
# send_text() and that its return value correctly gates delivery.
# All tests patch GovernanceGateService at its import path in
# mentor_message_service so no real Sentinel DB is required.
# ---------------------------------------------------------------------------


_GATE_PATCH = "services.mentor_message_service.GovernanceGateService"
_FAKE_SEND  = [
    {"success": True, "channel": "sms", "provider": "twilio",
     "provider_id": "SM1", "error": None, "recipient": "+1555"},
]


class TestGovernanceGateWiring:
    """GovernanceGateService must be called after the atomic claim and before
    send_text(). An approved gate must allow delivery; a non-approved gate must
    block it and return the governance_review_required shape. Gate exceptions
    must be fail-open. The gate must not be called on the already_claimed or
    no_db early-exit paths.
    """

    def test_approved_gate_calls_send_text(self):
        """Gate returns approved=True (approved_review) → send_text() must be called."""
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND) as mock_send, \
                 patch(_GATE_PATCH) as mock_gate:
                mock_gate.return_value.check_delivery_approved.return_value = {
                    "approved": True, "reason": "approved_review", "review_id": 42,
                }
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert mock_send.call_count == 1, \
                "send_text() must be called when gate returns approved=True"
        finally:
            _delete_triggered_user(cbm_id)

    def test_pending_gate_does_not_call_send_text(self):
        """Gate returns approved=False (pending) → send_text() must NOT be called."""
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND) as mock_send, \
                 patch(_GATE_PATCH) as mock_gate:
                mock_gate.return_value.check_delivery_approved.return_value = {
                    "approved": False, "reason": "pending", "review_id": 42,
                }
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert mock_send.call_count == 0, \
                "send_text() must NOT be called when gate returns approved=False"
        finally:
            _delete_triggered_user(cbm_id)

    def test_pending_gate_returns_governance_review_required_shape(self):
        """Gate returns approved=False → process_trigger() must return the
        governance_review_required shape: sent=False, reason=governance_review_required,
        review_id from the gate result, cbm_id of the trigger.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND), \
                 patch(_GATE_PATCH) as mock_gate:
                mock_gate.return_value.check_delivery_approved.return_value = {
                    "approved": False, "reason": "pending", "review_id": 42,
                }
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result["sent"]      is False
            assert result["reason"]    == "governance_review_required"
            assert result["review_id"] == 42
            assert result["cbm_id"]    == cbm_id
        finally:
            _delete_triggered_user(cbm_id)

    def test_no_sentinel_data_gate_calls_send_text(self):
        """Gate returns no_sentinel_data (approved=True) → send_text() must be called.
        Legacy students with no Sentinel interpretation must flow through normally.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND) as mock_send, \
                 patch(_GATE_PATCH) as mock_gate:
                mock_gate.return_value.check_delivery_approved.return_value = {
                    "approved": True, "reason": "no_sentinel_data", "review_id": None,
                }
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert mock_send.call_count == 1, \
                "send_text() must be called for no_sentinel_data (legacy fall-through)"
        finally:
            _delete_triggered_user(cbm_id)

    def test_gate_exception_is_fail_open_send_text_called(self):
        """If check_delivery_approved() raises, process_trigger() must be fail-open:
        send_text() must still be called. The gate must never drop a message.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND) as mock_send, \
                 patch(_GATE_PATCH) as mock_gate:
                mock_gate.return_value.check_delivery_approved.side_effect = RuntimeError(
                    "Sentinel DB unreachable"
                )
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert mock_send.call_count == 1, \
                "send_text() must be called when gate raises (fail-open)"
        finally:
            _delete_triggered_user(cbm_id)

    def test_gate_not_called_on_already_claimed_path(self):
        """The already_claimed path exits before delivery — gate must not fire
        for a trigger that was already processed by another worker.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND), \
                 patch(_GATE_PATCH) as mock_gate:
                mock_gate.return_value.check_delivery_approved.return_value = {
                    "approved": True, "reason": "approved_review", "review_id": 1,
                }
                from services.mentor_message_service import MentorMessageService
                svc = MentorMessageService()
                svc.process_trigger(cbm_id)   # winner — gate fires once
                svc.process_trigger(cbm_id)   # already_claimed — gate must not fire again

            assert mock_gate.return_value.check_delivery_approved.call_count == 1, \
                "Gate must be called exactly once; already_claimed path must skip it"
        finally:
            _delete_triggered_user(cbm_id)

    def test_gate_not_called_on_no_db_path(self):
        """MSSQL not configured → process_trigger() returns no_db immediately.
        Gate must never be called — no Sentinel session should be opened.
        """
        with patch("services.mentor_message_service.MSSQL_CONFIGURED", False), \
             patch(_GATE_PATCH) as mock_gate:
            from services.mentor_message_service import MentorMessageService
            result = MentorMessageService().process_trigger(cbm_id=999)

        assert result["reason"] == "no_db"
        mock_gate.return_value.check_delivery_approved.assert_not_called()

    def test_gate_error_outcome_calls_send_text(self):
        """Gate service returns {"approved": True, "reason": "gate_error", "review_id": None}
        — this is the gate-internal fail-open outcome, distinct from check_delivery_approved
        raising an exception. send_text() must still be called exactly once.
        """
        cbm_id = _insert_triggered_user()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND) as mock_send, \
                 patch(_GATE_PATCH) as mock_gate:
                mock_gate.return_value.check_delivery_approved.return_value = {
                    "approved": True, "reason": "gate_error", "review_id": None,
                }
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert mock_send.call_count == 1, (
                "send_text() must be called when gate returns gate_error (approved=True) — "
                "gate-level infrastructure failure must not drop the message"
            )
        finally:
            _delete_triggered_user(cbm_id)

    def test_gate_not_called_on_not_found_path(self):
        """TriggeredUser row does not exist → process_trigger() returns not_found immediately.
        Gate must never be called — the row was not claimed so no delivery is intended.
        """
        with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
             patch(_GATE_PATCH) as mock_gate:
            from services.mentor_message_service import MentorMessageService
            result = MentorMessageService().process_trigger(cbm_id=999999)

        assert result["reason"] == "not_found"
        mock_gate.return_value.check_delivery_approved.assert_not_called()

    def test_gate_called_with_string_entity_id_when_user_id_is_integer(self):
        """TriggeredUser.UserID is an Integer column. process_trigger() must cast it
        to str before passing to check_delivery_approved() — AIInterpretation.entity_id
        is String(100) and the two must match. Verifies the str(user_id) cast.
        """
        from config.database import SessionLocal
        from services.models import TriggeredUser

        with SessionLocal() as session:
            row = TriggeredUser(
                CB_ID=None, UserID=101, TriggerType="test_delivery_succeeded",
                TriggerLevel="Low", KPI=None, Severity=None,
                InsertDate=datetime.utcnow(), Completed=0, AgentID=None,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            cbm_id = row.CBM_ID

        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND), \
                 patch(_GATE_PATCH) as mock_gate:
                mock_gate.return_value.check_delivery_approved.return_value = {
                    "approved": True, "reason": "approved_review", "review_id": 1,
                }
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            mock_gate.return_value.check_delivery_approved.assert_called_once()
            call_kwargs = mock_gate.return_value.check_delivery_approved.call_args.kwargs
            assert call_kwargs["entity_id"] == "101", (
                f"entity_id must be str '101', got {call_kwargs['entity_id']!r} — "
                "process_trigger() must cast integer UserID to str before calling the gate"
            )
            assert isinstance(call_kwargs["entity_id"], str), (
                "entity_id must be a str, not an int — AIInterpretation.entity_id is String(100)"
            )
        finally:
            _delete_triggered_user(cbm_id)


# ---------------------------------------------------------------------------
# Delivery suppression helpers
# ---------------------------------------------------------------------------

def _ensure_student_responses_table() -> None:
    """Create AI_ChatBot_StudentResponses in the local SQLite DB if absent."""
    from config.database import engine
    from services.models import StudentResponse
    StudentResponse.__table__.create(engine, checkfirst=True)


def _insert_student_response(cbm_id: int, confidence: float) -> int:
    """Insert a minimal StudentResponse row and return its id."""
    from datetime import datetime
    from config.database import SessionLocal
    from services.models import StudentResponse
    _ensure_student_responses_table()
    with SessionLocal() as session:
        row = StudentResponse(
            cbm_id              = cbm_id,
            engagement_event_id = 9999,
            user_id             = 1,
            response_channel    = "sms",
            match_method        = "thread_id",
            confidence          = confidence,
            matched_at          = datetime.utcnow(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _delete_student_response(row_id: int) -> None:
    from config.database import SessionLocal
    from services.models import StudentResponse
    with SessionLocal() as session:
        row = session.get(StudentResponse, row_id)
        if row is not None:
            session.delete(row)
            session.commit()


# ---------------------------------------------------------------------------
# Delivery suppression tests (directive §12 / §3 / §6)
# ---------------------------------------------------------------------------

_FAKE_SEND_OK = [
    {"success": True, "channel": "sms", "provider": "twilio",
     "provider_id": "SM_SUPP", "error": None, "recipient": "+1555"},
]


class TestDeliverySuppression:
    """process_trigger() must suppress delivery only when a StudentResponse row
    exists for the exact cbm_id with confidence=1.0.

    Suppression occurs after the atomic claim and before the governance gate
    (directive §12 — delivery suppression reads only confidence=1.0 associations).
    """

    def test_confidence_1_suppresses_delivery_and_send_text_not_called(self):
        """StudentResponse.confidence=1.0 for this cbm_id → sent=False, reason=student_already_responded,
        send_text() not called.
        """
        cbm_id = _insert_triggered_user()
        sr_id  = _insert_student_response(cbm_id, confidence=1.0)
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND_OK) as mock_send:
                from services.mentor_message_service import MentorMessageService
                result = MentorMessageService().process_trigger(cbm_id)

            assert result == {"sent": False, "reason": "student_already_responded", "cbm_id": cbm_id}, \
                f"Expected suppression result, got {result}"
            assert mock_send.call_count == 0, \
                "send_text() must not be called when delivery is suppressed"
        finally:
            _delete_student_response(sr_id)
            _delete_triggered_user(cbm_id)

    def test_confidence_below_1_does_not_suppress_and_send_text_called(self):
        """StudentResponse.confidence<1.0 (heuristic) → delivery proceeds; send_text() is called.
        Low-confidence matches must never affect delivery decisions (directive §3, §6).
        """
        cbm_id = _insert_triggered_user()
        sr_id  = _insert_student_response(cbm_id, confidence=0.7)
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND_OK) as mock_send:
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert mock_send.call_count == 1, \
                "send_text() must be called when only a heuristic (confidence<1.0) row exists"
        finally:
            _delete_student_response(sr_id)
            _delete_triggered_user(cbm_id)

    def test_no_student_response_does_not_suppress_and_send_text_called(self):
        """No StudentResponse row for this cbm_id → delivery proceeds normally."""
        cbm_id = _insert_triggered_user()
        _ensure_student_responses_table()
        try:
            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND_OK) as mock_send:
                from services.mentor_message_service import MentorMessageService
                MentorMessageService().process_trigger(cbm_id)

            assert mock_send.call_count == 1, \
                "send_text() must be called when no StudentResponse exists for this cbm_id"
        finally:
            _delete_triggered_user(cbm_id)

    def test_suppression_query_error_fails_open_and_send_text_called(self):
        """If the suppression query raises, delivery must proceed — fail-open.
        SessionLocal call 2 (suppression) is made to raise; calls 1 and 3+
        use the real session so the claim and write-back succeed normally.
        """
        cbm_id = _insert_triggered_user()
        try:
            import services.mentor_message_service as svc_module
            original_sl  = svc_module.SessionLocal
            call_count   = {"n": 0}

            class _FailOnSecondCall:
                def __call__(self):
                    call_count["n"] += 1
                    if call_count["n"] == 2:
                        raise RuntimeError("simulated suppression query failure")
                    return original_sl()

            with patch("services.mentor_message_service.MSSQL_CONFIGURED", True), \
                 patch("services.mentor_message_service.OutboundDeliveryService.send_text",
                       return_value=_FAKE_SEND_OK) as mock_send:
                svc_module.SessionLocal = _FailOnSecondCall()
                try:
                    from services.mentor_message_service import MentorMessageService
                    MentorMessageService().process_trigger(cbm_id)
                finally:
                    svc_module.SessionLocal = original_sl

            assert mock_send.call_count == 1, \
                "send_text() must be called when suppression query raises (fail-open)"
        finally:
            _delete_triggered_user(cbm_id)
