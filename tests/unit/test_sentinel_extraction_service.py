"""Unit tests for SentinelExtractionService.

All tests are isolated — no database session, no network, no ORM migration.
The SQLAlchemy session is replaced with a MagicMock that controls what each
db.query().filter().first() / .all() call returns.

Test categories:
  - Top-level output shape and required keys
  - Unsupported entity_type → empty dimensions
  - Entity not found in TriggerData → empty dimensions
  - Engagement dimension: signals, risk inference, data_available
  - Retention risk dimension: signals, risk inference, submission rate
  - Communication responsiveness: completion rate, message counts
  - Intervention effectiveness: delivery log, completion rate
  - Missing data safe-defaults (None columns)
  - Signal summary aggregation
  - Risk inference helpers (unit-level)
  - _safe_float / _safe_int / _data_confidence / _empty_dimension helpers
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.sentinel_extraction_service import (
    SentinelExtractionService,
    _data_confidence,
    _empty_dimension,
    _safe_float,
    _safe_int,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SVC = SentinelExtractionService()

_ENTITY_ID   = "101"
_ENTITY_TYPE = "student"
_USER_ID     = 101


def _make_db() -> MagicMock:
    """Return a fresh MagicMock session with chainable .query().filter().first()/.all()."""
    db = MagicMock()
    # Default: queries return None / empty list
    q = MagicMock()
    q.filter.return_value = q
    q.first.return_value  = None
    q.all.return_value    = []
    db.query.return_value = q
    return db


def _trigger_data(**kwargs) -> SimpleNamespace:
    """Minimal TriggerData stub with sensible defaults."""
    defaults = dict(
        UserID=_USER_ID,
        FirstName="Jane",
        LastName="Doe",
        Email="jane@example.com",
        PhoneNumber="+15550001111",
        ActiveStatus="Y",
        StatusI="Active",
        StatusII="On track",
        Past10DaysLogon=5,
        LastActivityDays=2,
        LastLoginDays=2,
        DaysInStatus=30,
        HWsBehind=0,
        AttendancePercentage=92.0,
        AvgHWScore=85.0,
        AvgEffRating=4.2,
        NoOfAssignmentsSubmitted=8,
        TotalNoOfAssignments=10,
        Total_Payments=1500.0,
        PaymentBalance=0,
        IsClassActive=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _triggered_user(cbm_id=1, completed=1) -> SimpleNamespace:
    return SimpleNamespace(
        CBM_ID=cbm_id,
        UserID=_USER_ID,
        TriggerType="engagement",
        Completed=completed,
        CompletedDate=datetime(2025, 1, 10) if completed else None,
        InsertDate=datetime(2025, 1, 8),
    )


def _delivery_log(cbm_id=1, success=True, channel="sms") -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        cbm_id=cbm_id,
        user_id=_USER_ID,
        channel=channel,
        success=success,
        error_message=None,
    )


def _audit_log(entry_type="incoming_message") -> SimpleNamespace:
    return SimpleNamespace(
        entry_id=1,
        phone_number="+15550001111",
        entry_type=entry_type,
        Email="jane@example.com",
        Channel="sms",
    )


def _conversation_state() -> SimpleNamespace:
    return SimpleNamespace(
        PhoneNumber="+15550001111",
        Channel="whatsapp",
        LastUpdated=datetime(2025, 3, 15, 10, 0, 0),
    )


def _fingerprint(pattern_name="passive_disengagement", risk_level="medium") -> SimpleNamespace:
    return SimpleNamespace(
        entity_id=_ENTITY_ID,
        entity_type=_ENTITY_TYPE,
        pattern_name=pattern_name,
        score=0.72,
        risk_level=risk_level,
    )


_UNSET = object()  # sentinel: distinguishes "not provided" from "explicitly None"


def _make_full_db(
    td=_UNSET,
    triggered=_UNSET,
    delivery_logs=_UNSET,
    audit_logs=_UNSET,
    conv=_UNSET,
    fingerprints=_UNSET,
    engagement_events=_UNSET,
) -> MagicMock:
    """Return a mock session that routes queries to the right stub data.

    Pass None explicitly to simulate a table returning no rows.
    Omit a parameter (or pass _UNSET) to get the default stub data.
    """
    from services.models import (
        BehaviorFingerprint,
        ChatBotAuditLog,
        ConversationState,
        DeliveryLog,
        EngagementEvent,
        TriggerData,
        TriggeredUser,
    )

    if td               is _UNSET: td               = _trigger_data()
    if triggered        is _UNSET: triggered        = [_triggered_user()]
    if delivery_logs    is _UNSET: delivery_logs    = [_delivery_log()]
    if audit_logs       is _UNSET: audit_logs       = [_audit_log()]
    if conv             is _UNSET: conv             = _conversation_state()
    if fingerprints     is _UNSET: fingerprints     = [_fingerprint()]
    if engagement_events is _UNSET: engagement_events = []

    def _query_side_effect(*args):
        q = MagicMock()
        q.filter.return_value = q
        q.in_                 = MagicMock(return_value=True)

        # Resolve to ORM class: db.query(Model) passes the class directly;
        # db.query(Model.col1, Model.col2, ...) passes InstrumentedAttribute objects
        # whose .class_ property points back to the ORM class.
        first = args[0] if args else None
        model = getattr(first, "class_", first)

        if model is TriggerData:
            q.first.return_value = td
            q.all.return_value   = [td] if td else []
        elif model is TriggeredUser:
            q.first.return_value = triggered[0] if triggered else None
            q.all.return_value   = triggered
        elif model is DeliveryLog:
            q.first.return_value = delivery_logs[0] if delivery_logs else None
            q.all.return_value   = delivery_logs
        elif model is ChatBotAuditLog:
            q.first.return_value = audit_logs[0] if audit_logs else None
            q.all.return_value   = audit_logs
        elif model is ConversationState:
            q.first.return_value = conv
            q.all.return_value   = [conv] if conv else []
        elif model is BehaviorFingerprint:
            q.first.return_value = fingerprints[0] if fingerprints else None
            q.all.return_value   = fingerprints
        elif model is EngagementEvent:
            q.first.return_value = engagement_events[0] if engagement_events else None
            q.all.return_value   = engagement_events
        else:
            q.first.return_value = None
            q.all.return_value   = []
        return q

    db = MagicMock()
    db.query.side_effect = _query_side_effect
    return db


# ===========================================================================
# Top-level output shape
# ===========================================================================

class TestExtractStudentStateShape:
    def test_returns_all_required_top_level_keys(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        required = {"entity_id", "entity_type", "dimensions", "source_tables",
                    "extracted_at", "signal_summary"}
        assert required == set(result.keys())

    def test_entity_id_and_type_are_echoed(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["entity_id"]   == _ENTITY_ID
        assert result["entity_type"] == _ENTITY_TYPE

    def test_extracted_at_is_iso8601_string(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        # Must parse without raising
        datetime.fromisoformat(result["extracted_at"])

    def test_source_tables_is_nonempty_list(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert isinstance(result["source_tables"], list)
        assert len(result["source_tables"]) > 0

    def test_dimensions_contains_all_four_v1_keys(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        expected = {
            "engagement",
            "retention_risk",
            "communication_responsiveness",
            "intervention_effectiveness",
        }
        assert expected == set(result["dimensions"].keys())

    def test_signal_summary_has_required_keys(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        summary_keys = {
            "total_signals", "dimensions_with_data",
            "overall_confidence", "highest_risk_dimension",
            "highest_risk_level",
        }
        assert summary_keys == set(result["signal_summary"].keys())


# ===========================================================================
# Unsupported entity_type
# ===========================================================================

class TestUnsupportedEntityType:
    def test_unsupported_type_returns_no_data_dimensions(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, "42", "cohort")
        for dim in result["dimensions"].values():
            assert dim["data_available"] is False

    def test_unsupported_type_all_dimensions_risk_unknown(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, "42", "cohort")
        for dim in result["dimensions"].values():
            assert dim["risk_level"] == "unknown"

    def test_unsupported_type_all_dimensions_empty_signals(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, "42", "cohort")
        for dim in result["dimensions"].values():
            assert dim["signals"] == []


# ===========================================================================
# Entity not found in TriggerData
# ===========================================================================

class TestEntityNotFound:
    def test_missing_trigger_data_engagement_not_available(self):
        db = _make_full_db(td=None)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["data_available"] is False

    def test_missing_trigger_data_retention_not_available(self):
        db = _make_full_db(td=None)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["retention_risk"]["data_available"] is False

    def test_missing_trigger_data_engagement_risk_unknown(self):
        db = _make_full_db(td=None)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["risk_level"] == "unknown"

    def test_non_integer_entity_id_returns_empty_dimensions(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, "student_abc", _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["data_available"] is False
        assert result["dimensions"]["retention_risk"]["data_available"] is False


# ===========================================================================
# Engagement dimension
# ===========================================================================

class TestEngagementDimension:
    def test_data_available_is_true_when_trigger_data_exists(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["data_available"] is True

    def test_signals_list_is_nonempty(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert len(result["dimensions"]["engagement"]["signals"]) > 0

    def test_last_activity_days_signal_present(self):
        db = _make_full_db(td=_trigger_data(LastActivityDays=5))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["engagement"]["signals"]
        names = [s["name"] for s in signals]
        assert "last_activity_days" in names

    def test_low_risk_on_recent_activity(self):
        db = _make_full_db(td=_trigger_data(LastActivityDays=1, Past10DaysLogon=8))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["risk_level"] == "low"

    def test_medium_risk_on_3_to_6_days(self):
        db = _make_full_db(td=_trigger_data(LastActivityDays=5, Past10DaysLogon=2))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["risk_level"] == "medium"

    def test_high_risk_on_7_to_13_days(self):
        db = _make_full_db(td=_trigger_data(LastActivityDays=10, Past10DaysLogon=0))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["risk_level"] == "high"

    def test_critical_risk_on_14_plus_days(self):
        db = _make_full_db(td=_trigger_data(LastActivityDays=20, Past10DaysLogon=0))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["risk_level"] == "critical"

    def test_unknown_risk_when_all_activity_signals_null(self):
        db = _make_full_db(td=_trigger_data(LastActivityDays=None, Past10DaysLogon=None))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["risk_level"] == "unknown"

    def test_confidence_is_float_between_0_and_1(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        c = result["dimensions"]["engagement"]["confidence"]
        assert 0.0 <= c <= 1.0

    def test_confidence_lower_when_signals_are_null(self):
        full_td   = _trigger_data()
        sparse_td = _trigger_data(LastActivityDays=None, Past10DaysLogon=None,
                                   AttendancePercentage=None, LastLoginDays=None)
        db_full   = _make_full_db(td=full_td)
        db_sparse = _make_full_db(td=sparse_td)
        full_conf   = SVC.extract_student_state(db_full,   _ENTITY_ID, _ENTITY_TYPE)["dimensions"]["engagement"]["confidence"]
        sparse_conf = SVC.extract_student_state(db_sparse, _ENTITY_ID, _ENTITY_TYPE)["dimensions"]["engagement"]["confidence"]
        assert sparse_conf < full_conf

    def test_fingerprints_are_included(self):
        db = _make_full_db(fingerprints=[_fingerprint("disengaged", "high")])
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        fps = result["dimensions"]["engagement"]["fingerprints"]
        assert len(fps) == 1
        assert fps[0]["pattern_name"] == "disengaged"

    def test_fingerprints_empty_when_none_exist(self):
        db = _make_full_db(fingerprints=[])
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["fingerprints"] == []

    def test_source_record_count_is_1(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["engagement"]["source_record_count"] == 1


# ===========================================================================
# Retention risk dimension
# ===========================================================================

class TestRetentionRiskDimension:
    def test_data_available_when_trigger_data_exists(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["retention_risk"]["data_available"] is True

    def test_low_risk_on_zero_hw_behind(self):
        db = _make_full_db(td=_trigger_data(HWsBehind=0, AvgHWScore=90.0))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["retention_risk"]["risk_level"] == "low"

    def test_medium_risk_on_1_hw_behind(self):
        db = _make_full_db(td=_trigger_data(HWsBehind=1, AvgHWScore=75.0))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["retention_risk"]["risk_level"] == "medium"

    def test_high_risk_on_3_hw_behind(self):
        db = _make_full_db(td=_trigger_data(HWsBehind=3, AvgHWScore=60.0))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["retention_risk"]["risk_level"] == "high"

    def test_critical_risk_on_5_hw_behind(self):
        db = _make_full_db(td=_trigger_data(HWsBehind=5, AvgHWScore=40.0))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["retention_risk"]["risk_level"] == "critical"

    def test_submission_rate_computed_from_submitted_and_total(self):
        db = _make_full_db(td=_trigger_data(
            NoOfAssignmentsSubmitted=6, TotalNoOfAssignments=10
        ))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["retention_risk"]["signals"]
        sr = next(s for s in signals if s["name"] == "submission_rate")
        assert sr["value"] == pytest.approx(0.60)

    def test_submission_rate_none_when_total_is_zero(self):
        db = _make_full_db(td=_trigger_data(
            NoOfAssignmentsSubmitted=0, TotalNoOfAssignments=0
        ))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["retention_risk"]["signals"]
        sr = next(s for s in signals if s["name"] == "submission_rate")
        assert sr["value"] is None

    def test_submission_rate_none_when_total_is_null(self):
        db = _make_full_db(td=_trigger_data(
            NoOfAssignmentsSubmitted=None, TotalNoOfAssignments=None
        ))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["retention_risk"]["signals"]
        sr = next(s for s in signals if s["name"] == "submission_rate")
        assert sr["value"] is None

    def test_low_submission_rate_escalates_to_high(self):
        # HWsBehind=0 (would be low) but very low submission rate → high
        db = _make_full_db(td=_trigger_data(
            HWsBehind=0,
            NoOfAssignmentsSubmitted=2, TotalNoOfAssignments=10,
        ))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["retention_risk"]["risk_level"] == "high"

    def test_unknown_risk_when_all_retention_signals_null(self):
        db = _make_full_db(td=_trigger_data(
            HWsBehind=None, AvgHWScore=None,
            NoOfAssignmentsSubmitted=None, TotalNoOfAssignments=None,
        ))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["retention_risk"]["risk_level"] == "unknown"

    def test_status_ii_excerpt_truncated_to_120_chars(self):
        long_text = "X" * 300
        db = _make_full_db(td=_trigger_data(StatusII=long_text))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["retention_risk"]["signals"]
        excerpt = next(s for s in signals if s["name"] == "status_ii_excerpt")
        assert excerpt["value"] == "X" * 120


# ===========================================================================
# Communication responsiveness dimension
# ===========================================================================

class TestCommunicationResponsivenessDimension:
    def test_data_available_when_triggers_exist(self):
        db = _make_full_db(triggered=[_triggered_user()])
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["communication_responsiveness"]["data_available"] is True

    def test_unknown_risk_when_no_triggers_and_no_messages(self):
        db = _make_full_db(triggered=[], audit_logs=[], conv=None)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["communication_responsiveness"]["risk_level"] == "unknown"

    def test_low_risk_on_high_completion_rate(self):
        triggers = [_triggered_user(cbm_id=i, completed=1) for i in range(1, 5)]
        db = _make_full_db(triggered=triggers)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["communication_responsiveness"]["risk_level"] == "low"

    def test_medium_risk_on_partial_completion_rate(self):
        triggers = [
            _triggered_user(cbm_id=1, completed=1),
            _triggered_user(cbm_id=2, completed=0),
            _triggered_user(cbm_id=3, completed=0),
        ]
        db = _make_full_db(triggered=triggers)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["communication_responsiveness"]["risk_level"] == "medium"

    def test_high_risk_on_zero_completion_rate(self):
        triggers = [
            _triggered_user(cbm_id=1, completed=0),
            _triggered_user(cbm_id=2, completed=0),
        ]
        db = _make_full_db(triggered=triggers)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["communication_responsiveness"]["risk_level"] == "high"

    def test_inbound_count_signal_present(self):
        audit = [_audit_log("incoming_message"), _audit_log("incoming_message")]
        db = _make_full_db(audit_logs=audit)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["communication_responsiveness"]["signals"]
        inbound = next(s for s in signals if s["name"] == "inbound_message_count")
        assert inbound["value"] == 2

    def test_channel_signal_from_conversation_state(self):
        db = _make_full_db(conv=_conversation_state())
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["communication_responsiveness"]["signals"]
        channel_sig = next(s for s in signals if s["name"] == "active_channel")
        assert channel_sig["value"] == "whatsapp"

    def test_last_conversation_updated_is_isoformat(self):
        db = _make_full_db(conv=_conversation_state())
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["communication_responsiveness"]["signals"]
        ts_sig  = next(s for s in signals if s["name"] == "last_conversation_updated")
        # Must be parseable
        assert ts_sig["value"] is not None
        datetime.fromisoformat(ts_sig["value"])


# ===========================================================================
# Intervention effectiveness dimension
# ===========================================================================

class TestInterventionEffectivenessDimension:
    def test_data_available_when_triggers_exist(self):
        db = _make_full_db(triggered=[_triggered_user()])
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["intervention_effectiveness"]["data_available"] is True

    def test_unknown_risk_with_no_triggers(self):
        db = _make_full_db(triggered=[], delivery_logs=[], engagement_events=[])
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["intervention_effectiveness"]["risk_level"] == "unknown"

    def test_low_risk_on_high_delivery_success_rate(self):
        triggered = [_triggered_user(cbm_id=i, completed=1) for i in range(1, 4)]
        logs = [_delivery_log(cbm_id=i, success=True) for i in range(1, 4)]
        db = _make_full_db(triggered=triggered, delivery_logs=logs)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["intervention_effectiveness"]["risk_level"] == "low"

    def test_medium_risk_on_partial_delivery_success(self):
        triggered = [_triggered_user(cbm_id=i, completed=1) for i in range(1, 5)]
        logs = [
            _delivery_log(cbm_id=1, success=True),
            _delivery_log(cbm_id=2, success=False),
            _delivery_log(cbm_id=3, success=False),
        ]
        db = _make_full_db(triggered=triggered, delivery_logs=logs)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["intervention_effectiveness"]["risk_level"] == "medium"

    def test_high_risk_on_zero_delivery_success(self):
        triggered = [_triggered_user(cbm_id=i) for i in range(1, 3)]
        logs = [_delivery_log(cbm_id=i, success=False) for i in range(1, 3)]
        db = _make_full_db(triggered=triggered, delivery_logs=logs)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["dimensions"]["intervention_effectiveness"]["risk_level"] == "high"

    def test_delivery_success_rate_signal_present(self):
        triggered = [_triggered_user(cbm_id=1)]
        logs = [_delivery_log(cbm_id=1, success=True)]
        db = _make_full_db(triggered=triggered, delivery_logs=logs)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["intervention_effectiveness"]["signals"]
        dl_sig = next(s for s in signals if s["name"] == "delivery_log_success_rate")
        assert dl_sig["value"] == pytest.approx(1.0)

    def test_channels_used_collected_from_delivery_log(self):
        triggered = [_triggered_user(cbm_id=i) for i in range(1, 3)]
        logs = [
            _delivery_log(cbm_id=1, success=True, channel="sms"),
            _delivery_log(cbm_id=2, success=True, channel="whatsapp"),
        ]
        db = _make_full_db(triggered=triggered, delivery_logs=logs)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        signals = result["dimensions"]["intervention_effectiveness"]["signals"]
        ch_sig  = next(s for s in signals if s["name"] == "channels_used")
        assert set(ch_sig["value"]) == {"sms", "whatsapp"}

    def test_source_record_count_includes_delivery_and_events(self):
        triggered = [_triggered_user(cbm_id=1)]
        logs      = [_delivery_log(cbm_id=1)]
        db = _make_full_db(triggered=triggered, delivery_logs=logs)
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        # 1 trigger + 1 delivery = 2 minimum
        assert result["dimensions"]["intervention_effectiveness"]["source_record_count"] >= 2


# ===========================================================================
# Signal summary aggregation
# ===========================================================================

class TestSignalSummary:
    def test_total_signals_sums_across_dimensions(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        expected = sum(
            len(d["signals"]) for d in result["dimensions"].values()
        )
        assert result["signal_summary"]["total_signals"] == expected

    def test_dimensions_with_data_counts_available_only(self):
        db = _make_full_db(td=None)   # TriggerData missing → eng + retention empty
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        # At most 2 dims can have data (comm + intervention via TriggeredUser)
        assert result["signal_summary"]["dimensions_with_data"] <= 2

    def test_highest_risk_dimension_identifies_worst(self):
        # engagement = critical (LastActivityDays=20)
        db = _make_full_db(td=_trigger_data(LastActivityDays=20, HWsBehind=0))
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["signal_summary"]["highest_risk_level"] == "critical"
        assert result["signal_summary"]["highest_risk_dimension"] == "engagement"

    def test_overall_confidence_is_mean_of_dimension_confidences(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, _ENTITY_TYPE)
        dims = result["dimensions"]
        expected_mean = sum(d["confidence"] for d in dims.values()) / len(dims)
        assert result["signal_summary"]["overall_confidence"] == pytest.approx(
            round(expected_mean, 4), abs=1e-6
        )

    def test_unsupported_entity_type_highest_risk_is_unknown(self):
        db = _make_full_db()
        result = SVC.extract_student_state(db, _ENTITY_ID, "cohort")
        assert result["signal_summary"]["highest_risk_level"] == "unknown"


# ===========================================================================
# Risk inference helpers (unit-level)
# ===========================================================================

class TestInferEngagementRisk:
    def test_critical_at_14_days(self):
        assert SVC._infer_engagement_risk(14, 0, "Y") == "critical"

    def test_high_at_7_days(self):
        assert SVC._infer_engagement_risk(7, 0, "Y") == "high"

    def test_medium_at_3_days(self):
        assert SVC._infer_engagement_risk(3, 5, "Y") == "medium"

    def test_low_at_2_days(self):
        assert SVC._infer_engagement_risk(2, 5, "Y") == "low"

    def test_unknown_when_both_signals_none(self):
        assert SVC._infer_engagement_risk(None, None, None) == "unknown"

    def test_high_when_logon_is_zero_and_activity_none(self):
        assert SVC._infer_engagement_risk(None, 0, "Y") == "high"


class TestInferRetentionRisk:
    def test_critical_at_5_hw_behind(self):
        assert SVC._infer_retention_risk(5, 70.0, 0.9) == "critical"

    def test_high_at_3_hw_behind(self):
        assert SVC._infer_retention_risk(3, 65.0, 0.8) == "high"

    def test_medium_at_1_hw_behind(self):
        assert SVC._infer_retention_risk(1, 80.0, 0.9) == "medium"

    def test_low_at_0_hw_behind(self):
        assert SVC._infer_retention_risk(0, 88.0, 0.9) == "low"

    def test_unknown_when_all_signals_none(self):
        assert SVC._infer_retention_risk(None, None, None) == "unknown"

    def test_submission_rate_escalates_when_hw_behind_zero(self):
        assert SVC._infer_retention_risk(0, 90.0, 0.20) == "high"


class TestInferCommunicationRisk:
    def test_unknown_when_no_triggers(self):
        assert SVC._infer_communication_risk(None, 0) == "unknown"

    def test_high_when_completion_rate_zero(self):
        assert SVC._infer_communication_risk(0.0, 3) == "high"

    def test_medium_when_below_threshold(self):
        assert SVC._infer_communication_risk(0.30, 4) == "medium"

    def test_low_when_above_threshold(self):
        assert SVC._infer_communication_risk(0.80, 5) == "low"


class TestInferInterventionRisk:
    def test_unknown_when_no_triggers(self):
        assert SVC._infer_intervention_risk(None, None, 0) == "unknown"

    def test_high_when_dl_success_rate_zero(self):
        assert SVC._infer_intervention_risk(0.9, 0.0, 3) == "high"

    def test_medium_when_dl_below_threshold(self):
        assert SVC._infer_intervention_risk(0.9, 0.30, 3) == "medium"

    def test_low_when_dl_above_threshold(self):
        assert SVC._infer_intervention_risk(0.9, 0.90, 3) == "low"

    def test_falls_back_to_completion_rate_when_no_dl(self):
        assert SVC._infer_intervention_risk(0.0, None, 3) == "high"


# ===========================================================================
# Module-level helper functions
# ===========================================================================

class TestSafeFloat:
    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_int_coerced_to_float(self):
        assert _safe_float(3) == 3.0

    def test_string_numeric_coerced(self):
        assert _safe_float("2.5") == 2.5

    def test_non_numeric_string_returns_default(self):
        assert _safe_float("bad") == 0.0

    def test_custom_default(self):
        assert _safe_float(None, default=-1.0) == -1.0


class TestSafeInt:
    def test_none_returns_default(self):
        assert _safe_int(None) == 0

    def test_float_truncated(self):
        assert _safe_int(3.9) == 3

    def test_non_numeric_returns_default(self):
        assert _safe_int("abc") == 0

    def test_custom_default(self):
        assert _safe_int(None, default=99) == 99


class TestDataConfidence:
    def test_zero_total_returns_zero(self):
        assert _data_confidence(0, 0) == 0.0

    def test_all_present(self):
        assert _data_confidence(7, 7) == 1.0

    def test_partial(self):
        assert _data_confidence(3, 6) == pytest.approx(0.5)

    def test_clamped_above_one(self):
        assert _data_confidence(10, 7) == 1.0

    def test_clamped_below_zero(self):
        assert _data_confidence(-1, 5) == 0.0


class TestEmptyDimension:
    def test_has_all_required_keys(self):
        dim = _empty_dimension()
        required = {"signals", "risk_level", "confidence", "fingerprints",
                    "data_available", "source_record_count", "notes"}
        assert required == set(dim.keys())

    def test_data_available_is_false(self):
        assert _empty_dimension()["data_available"] is False

    def test_risk_level_is_unknown(self):
        assert _empty_dimension()["risk_level"] == "unknown"

    def test_signals_and_fingerprints_are_empty_lists(self):
        dim = _empty_dimension()
        assert dim["signals"]      == []
        assert dim["fingerprints"] == []

    def test_confidence_is_zero(self):
        assert _empty_dimension()["confidence"] == 0.0

    def test_custom_notes_passed_through(self):
        assert _empty_dimension("custom msg")["notes"] == "custom msg"
