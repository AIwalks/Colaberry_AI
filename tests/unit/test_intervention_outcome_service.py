"""Unit tests for InterventionOutcomeService.

All tests use mocked DB sessions — no live DB or MSSQL required.

Coverage
────────
- Enrollment happy path (fields, window, delivery gate)
- Duplicate prevention (idempotent no-op on second call)
- Before-state resolution (interpretation → trigger_data → unavailable)
- Snapshot parsing (both payload shapes, edge cases)
- Outcome classification (improved, not_improved)
- Inconclusive outcomes (4 distinct cases)
- Evaluation of multiple pending records
- Defensive behaviour (no crash on DB errors)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import MagicMock, call

import pytest

from services.intervention_outcome_service import InterventionOutcomeService
from services.models import AIInterpretation, InterventionOutcome, TriggerData


# ===========================================================================
# Shared helpers
# ===========================================================================

_NOW      = datetime(2026, 5, 28, 12, 0, 0)
_WIN_START = _NOW - timedelta(days=15)
_WIN_END   = _WIN_START + timedelta(days=14)


def _svc() -> InterventionOutcomeService:
    return InterventionOutcomeService()


def _make_db(
    *,
    existing_outcome: Optional[Any] = None,
    interpretation:   Optional[Any] = None,
    trigger_data:     Optional[Any] = None,
    pending_records:  Optional[list] = None,
) -> MagicMock:
    """Build a mock DB whose .query() dispatches by model class.

    Supports both enrollment queries (.first()) and evaluation queries (.all()).
    """
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        if model is InterventionOutcome:
            q.filter.return_value.first.return_value = existing_outcome
            q.filter.return_value.all.return_value   = pending_records or []
        elif model is AIInterpretation:
            q.filter.return_value.order_by.return_value.first.return_value = interpretation
        elif model is TriggerData:
            q.filter.return_value.first.return_value = trigger_data
        return q

    db.query.side_effect = _query
    return db


def _make_interpretation(
    *,
    interp_id: int = 99,
    risk_level: str = "high",
    activity_days: Optional[int] = 18,
) -> SimpleNamespace:
    """Create a fake AIInterpretation row with source_snapshot_json populated."""
    snapshot = {}
    if activity_days is not None:
        snapshot = {"kpis": [{"kpi_name": "last_activity_days", "value": activity_days}]}
    return SimpleNamespace(
        id               = interp_id,
        risk_level       = risk_level,
        source_snapshot_json = json.dumps(snapshot),
    )


def _make_trigger_data(*, activity_days: Optional[int] = 18) -> SimpleNamespace:
    return SimpleNamespace(UserID=42, LastActivityDays=activity_days)


def _make_pending_record(
    *,
    cbm_id: int = 1,
    user_id: int = 42,
    delivery_gate_passed: bool = True,
    before_last_activity_days: Optional[int] = 18,
    before_snapshot_source: str = "interpretation",
) -> InterventionOutcome:
    """Construct an InterventionOutcome in 'pending' state (no DB needed)."""
    return InterventionOutcome(
        cbm_id                    = cbm_id,
        user_id                   = user_id,
        delivery_gate_passed      = delivery_gate_passed,
        before_last_activity_days = before_last_activity_days,
        before_risk_level         = "high",
        before_snapshot_source    = before_snapshot_source,
        window_start              = _WIN_START,
        window_end                = _WIN_END,
        evaluation_window_days    = 14,
        outcome                   = "pending",
        eligible_for_learning     = None,
        created_at                = _WIN_START,
        updated_at                = _WIN_START,
    )


# ===========================================================================
# Enrollment — happy path
# ===========================================================================

class TestEnrollmentHappyPath:

    def test_db_add_and_commit_called(self):
        db = _make_db(interpretation=_make_interpretation())
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        db.add.assert_called_once()
        db.commit.assert_called()

    def test_returns_record_after_commit(self):
        db = _make_db(interpretation=_make_interpretation())
        result = _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                               window_start=_WIN_START)
        assert result is not None

    def test_record_has_correct_cbm_id(self):
        db = _make_db(interpretation=_make_interpretation())
        _svc().enroll(db, cbm_id=77, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.cbm_id == 77

    def test_record_has_correct_user_id(self):
        db = _make_db(interpretation=_make_interpretation())
        _svc().enroll(db, cbm_id=1, user_id=55, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.user_id == 55

    def test_outcome_is_pending_at_enrollment(self):
        db = _make_db(interpretation=_make_interpretation())
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.outcome == "pending"

    def test_eligible_for_learning_is_none_at_enrollment(self):
        db = _make_db(interpretation=_make_interpretation())
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.eligible_for_learning is None

    def test_window_end_equals_start_plus_window_days(self):
        db = _make_db(interpretation=_make_interpretation())
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START, evaluation_window_days=14)
        record = db.add.call_args[0][0]
        assert record.window_end == _WIN_START + timedelta(days=14)

    def test_custom_window_days_stored_on_record(self):
        db = _make_db(interpretation=_make_interpretation())
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START, evaluation_window_days=21)
        record = db.add.call_args[0][0]
        assert record.evaluation_window_days == 21

    def test_window_start_copied_to_record(self):
        db = _make_db(interpretation=_make_interpretation())
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.window_start == _WIN_START


# ===========================================================================
# Enrollment — delivery gate
# ===========================================================================

class TestEnrollmentDeliveryGate:

    def test_gate_true_when_delivery_succeeded_true(self):
        db = _make_db()
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.delivery_gate_passed is True

    def test_gate_false_when_delivery_succeeded_false(self):
        db = _make_db()
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=False,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.delivery_gate_passed is False

    def test_gate_false_when_delivery_succeeded_none(self):
        """None means no delivery was attempted — gate must not pass."""
        db = _make_db()
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=None,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.delivery_gate_passed is False


# ===========================================================================
# Duplicate prevention
# ===========================================================================

class TestDuplicatePrevention:

    def test_existing_record_returned_without_add(self):
        existing = _make_pending_record()
        db = _make_db(existing_outcome=existing)
        result = _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                               window_start=_WIN_START)
        db.add.assert_not_called()
        assert result is existing

    def test_existing_record_returned_without_commit(self):
        existing = _make_pending_record()
        db = _make_db(existing_outcome=existing)
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        db.commit.assert_not_called()

    def test_second_enroll_returns_existing_record(self):
        """Simulates calling enroll() twice for the same cbm_id."""
        db = _make_db(interpretation=_make_interpretation())

        # First call — no existing record
        first = _svc().enroll(db, cbm_id=5, user_id=42, delivery_succeeded=True,
                              window_start=_WIN_START)

        # Second call — existing record is the record from the first call
        existing = db.add.call_args[0][0]
        db2 = _make_db(existing_outcome=existing)
        second = _svc().enroll(db2, cbm_id=5, user_id=42, delivery_succeeded=True,
                               window_start=_WIN_START)

        db2.add.assert_not_called()
        assert second is existing


# ===========================================================================
# Before-state resolution
# ===========================================================================

class TestBeforeStateResolution:

    def test_uses_interpretation_source_when_available(self):
        interp = _make_interpretation(activity_days=20)
        db = _make_db(interpretation=interp)
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.before_snapshot_source == "interpretation"
        assert record.before_last_activity_days == 20

    def test_stores_interpretation_id_when_interpretation_found(self):
        interp = _make_interpretation(interp_id=77, activity_days=18)
        db = _make_db(interpretation=interp)
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.interpretation_id == 77

    def test_stores_before_risk_level_from_interpretation(self):
        interp = _make_interpretation(risk_level="critical", activity_days=25)
        db = _make_db(interpretation=interp)
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.before_risk_level == "critical"

    def test_falls_back_to_trigger_data_when_no_interpretation(self):
        td = _make_trigger_data(activity_days=15)
        db = _make_db(interpretation=None, trigger_data=td)
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.before_snapshot_source == "trigger_data"
        assert record.before_last_activity_days == 15

    def test_trigger_data_fallback_sets_no_interpretation_id(self):
        td = _make_trigger_data(activity_days=15)
        db = _make_db(interpretation=None, trigger_data=td)
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.interpretation_id is None

    def test_sets_unavailable_when_no_source_exists(self):
        db = _make_db(interpretation=None, trigger_data=None)
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.before_snapshot_source == "unavailable"
        assert record.before_last_activity_days is None

    def test_null_user_id_sets_unavailable_without_querying(self):
        db = _make_db()
        _svc().enroll(db, cbm_id=1, user_id=None, delivery_succeeded=True,
                      window_start=_WIN_START)
        record = db.add.call_args[0][0]
        assert record.before_snapshot_source == "unavailable"
        assert record.before_last_activity_days is None

    def test_null_user_id_still_creates_record(self):
        """UserID=NULL rows must still be enrolled — they just become inconclusive later."""
        db = _make_db()
        result = _svc().enroll(db, cbm_id=1, user_id=None, delivery_succeeded=True,
                               window_start=_WIN_START)
        db.add.assert_called_once()
        assert result is not None


# ===========================================================================
# Snapshot parsing
# ===========================================================================

class TestSnapshotParsing:

    _svc = InterventionOutcomeService

    def test_parses_activity_days_from_kpis_shape(self):
        snap = json.dumps({"kpis": [
            {"kpi_name": "last_activity_days", "value": 18},
            {"kpi_name": "attendance_percentage", "value": 0.85},
        ]})
        assert self._svc._extract_activity_days_from_snapshot(snap) == 18

    def test_parses_activity_days_from_dimensions_shape(self):
        snap = json.dumps({"dimensions": {"engagement": {"signals": [
            {"name": "last_activity_days", "value": 22, "unit": "days"},
            {"name": "last_login_days",    "value": 10, "unit": "days"},
        ]}}})
        assert self._svc._extract_activity_days_from_snapshot(snap) == 22

    def test_kpis_shape_takes_priority_over_dimensions(self):
        snap = json.dumps({
            "kpis": [{"kpi_name": "last_activity_days", "value": 10}],
            "dimensions": {"engagement": {"signals": [
                {"name": "last_activity_days", "value": 20}
            ]}},
        })
        assert self._svc._extract_activity_days_from_snapshot(snap) == 10

    def test_returns_none_for_empty_string(self):
        assert self._svc._extract_activity_days_from_snapshot("") is None

    def test_returns_none_for_invalid_json(self):
        assert self._svc._extract_activity_days_from_snapshot("{not json}") is None

    def test_returns_none_when_kpi_name_not_present(self):
        snap = json.dumps({"kpis": [{"kpi_name": "attendance_percentage", "value": 0.9}]})
        assert self._svc._extract_activity_days_from_snapshot(snap) is None

    def test_returns_none_for_empty_kpis_list(self):
        assert self._svc._extract_activity_days_from_snapshot(json.dumps({"kpis": []})) is None

    def test_coerces_string_value_to_int(self):
        snap = json.dumps({"kpis": [{"kpi_name": "last_activity_days", "value": "14"}]})
        assert self._svc._extract_activity_days_from_snapshot(snap) == 14

    def test_returns_none_for_non_numeric_value(self):
        snap = json.dumps({"kpis": [{"kpi_name": "last_activity_days", "value": "N/A"}]})
        assert self._svc._extract_activity_days_from_snapshot(snap) is None


# ===========================================================================
# Outcome classification — improved
# ===========================================================================

class TestImprovedOutcome:

    def _eval_record(self, before: int, after_activity: int,
                     minimum_delta_days: int = 3) -> InterventionOutcome:
        record = _make_pending_record(before_last_activity_days=before)
        td = _make_trigger_data(activity_days=after_activity)
        db = _make_db(pending_records=[record], trigger_data=td)
        _svc().evaluate_ready_outcomes(db, minimum_delta_days=minimum_delta_days)
        return record

    def test_improved_when_delta_equals_threshold(self):
        record = self._eval_record(before=18, after_activity=15, minimum_delta_days=3)
        assert record.outcome == "improved"

    def test_improved_when_delta_exceeds_threshold(self):
        record = self._eval_record(before=20, after_activity=5)
        assert record.outcome == "improved"

    def test_improved_sets_eligible_for_learning_true(self):
        record = self._eval_record(before=18, after_activity=10)
        assert record.eligible_for_learning is True

    def test_improved_sets_after_last_activity_days(self):
        record = self._eval_record(before=18, after_activity=10)
        assert record.after_last_activity_days == 10

    def test_improved_sets_evaluated_at(self):
        record = self._eval_record(before=18, after_activity=10)
        assert record.evaluated_at is not None

    def test_improved_reason_contains_before_and_after_values(self):
        record = self._eval_record(before=18, after_activity=10)
        assert "18" in record.outcome_reason
        assert "10" in record.outcome_reason

    def test_custom_minimum_delta_respected(self):
        """With minimum_delta_days=1, delta=1 is sufficient for improved."""
        record = self._eval_record(before=10, after_activity=9, minimum_delta_days=1)
        assert record.outcome == "improved"


# ===========================================================================
# Outcome classification — not_improved
# ===========================================================================

class TestNotImprovedOutcome:

    def _eval_record(self, before: int, after_activity: int,
                     minimum_delta_days: int = 3) -> InterventionOutcome:
        record = _make_pending_record(before_last_activity_days=before)
        td = _make_trigger_data(activity_days=after_activity)
        db = _make_db(pending_records=[record], trigger_data=td)
        _svc().evaluate_ready_outcomes(db, minimum_delta_days=minimum_delta_days)
        return record

    def test_not_improved_when_delta_below_threshold(self):
        record = self._eval_record(before=18, after_activity=16, minimum_delta_days=3)
        assert record.outcome == "not_improved"

    def test_not_improved_when_no_change(self):
        record = self._eval_record(before=18, after_activity=18)
        assert record.outcome == "not_improved"

    def test_not_improved_when_activity_increased(self):
        """Student is more inactive after intervention — no improvement."""
        record = self._eval_record(before=18, after_activity=25)
        assert record.outcome == "not_improved"

    def test_not_improved_sets_eligible_for_learning_true(self):
        """not_improved is still a valid labeled example for learning."""
        record = self._eval_record(before=18, after_activity=17)
        assert record.eligible_for_learning is True

    def test_not_improved_sets_after_last_activity_days(self):
        record = self._eval_record(before=18, after_activity=20)
        assert record.after_last_activity_days == 20

    def test_not_improved_reason_references_threshold(self):
        record = self._eval_record(before=18, after_activity=16, minimum_delta_days=3)
        assert "3" in record.outcome_reason


# ===========================================================================
# Inconclusive outcomes
# ===========================================================================

class TestInconclusiveOutcomes:

    def _eval_record(self, record: InterventionOutcome,
                     after_activity: Optional[int] = 10) -> InterventionOutcome:
        td = _make_trigger_data(activity_days=after_activity)
        db = _make_db(pending_records=[record], trigger_data=td)
        _svc().evaluate_ready_outcomes(db)
        return record

    def test_inconclusive_when_delivery_gate_false(self):
        record = _make_pending_record(delivery_gate_passed=False,
                                      before_last_activity_days=18)
        self._eval_record(record)
        assert record.outcome == "inconclusive"

    def test_delivery_gate_false_sets_eligible_false(self):
        record = _make_pending_record(delivery_gate_passed=False,
                                      before_last_activity_days=18)
        self._eval_record(record)
        assert record.eligible_for_learning is False

    def test_inconclusive_when_before_state_none(self):
        record = _make_pending_record(delivery_gate_passed=True,
                                      before_last_activity_days=None)
        self._eval_record(record)
        assert record.outcome == "inconclusive"

    def test_before_state_none_sets_eligible_false(self):
        record = _make_pending_record(before_last_activity_days=None)
        self._eval_record(record)
        assert record.eligible_for_learning is False

    def test_inconclusive_when_student_already_healthy_at_zero(self):
        record = _make_pending_record(before_last_activity_days=0)
        self._eval_record(record)
        assert record.outcome == "inconclusive"

    def test_inconclusive_when_student_already_healthy_at_threshold(self):
        """before_last_activity_days = 3 is exactly the healthy threshold."""
        record = _make_pending_record(before_last_activity_days=3)
        self._eval_record(record)
        assert record.outcome == "inconclusive"

    def test_inconclusive_when_student_already_healthy_reason_contains_days(self):
        record = _make_pending_record(before_last_activity_days=2)
        self._eval_record(record)
        assert "2" in record.outcome_reason

    def test_inconclusive_when_after_state_unavailable(self):
        record = _make_pending_record(before_last_activity_days=18)
        # after_activity=None means TriggerData returns no row
        self._eval_record(record, after_activity=None)
        assert record.outcome == "inconclusive"

    def test_after_state_unavailable_sets_eligible_false(self):
        record = _make_pending_record(before_last_activity_days=18)
        self._eval_record(record, after_activity=None)
        assert record.eligible_for_learning is False

    def test_inconclusive_records_are_not_eligible_for_learning(self):
        """All four inconclusive cases must set eligible_for_learning=False."""
        cases = [
            _make_pending_record(delivery_gate_passed=False, before_last_activity_days=18),
            _make_pending_record(before_last_activity_days=None),
            _make_pending_record(before_last_activity_days=2),
        ]
        for record in cases:
            td = _make_trigger_data(activity_days=10)
            db = _make_db(pending_records=[record], trigger_data=td)
            _svc().evaluate_ready_outcomes(db)
            assert record.eligible_for_learning is False, (
                f"Expected eligible_for_learning=False for {record.before_last_activity_days}"
            )


# ===========================================================================
# evaluate_ready_outcomes — batch behaviour
# ===========================================================================

class TestEvaluateReadyOutcomes:

    def test_returns_count_of_evaluated_records(self):
        records = [
            _make_pending_record(cbm_id=1),
            _make_pending_record(cbm_id=2),
        ]
        td = _make_trigger_data(activity_days=5)
        db = _make_db(pending_records=records, trigger_data=td)
        count = _svc().evaluate_ready_outcomes(db)
        assert count == 2

    def test_returns_zero_for_empty_pending_set(self):
        db = _make_db(pending_records=[])
        count = _svc().evaluate_ready_outcomes(db)
        assert count == 0

    def test_db_commit_called_for_each_evaluated_record(self):
        records = [_make_pending_record(cbm_id=i) for i in range(1, 4)]
        td = _make_trigger_data(activity_days=5)
        db = _make_db(pending_records=records, trigger_data=td)
        _svc().evaluate_ready_outcomes(db)
        # At minimum one commit per record
        assert db.commit.call_count >= 3

    def test_all_records_in_batch_are_evaluated(self):
        records = [
            _make_pending_record(cbm_id=1, before_last_activity_days=18),
            _make_pending_record(cbm_id=2, delivery_gate_passed=False, before_last_activity_days=18),
            _make_pending_record(cbm_id=3, before_last_activity_days=2),
        ]
        td = _make_trigger_data(activity_days=5)
        db = _make_db(pending_records=records, trigger_data=td)
        _svc().evaluate_ready_outcomes(db)
        for r in records:
            assert r.outcome != "pending", f"Record cbm_id={r.cbm_id} was not evaluated"


# ===========================================================================
# Defensive behaviour — no crash on DB errors
# ===========================================================================

class TestDefensiveness:

    def test_enroll_returns_none_when_db_add_raises(self):
        db = _make_db()
        db.add.side_effect = RuntimeError("simulated DB failure")
        result = _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                               window_start=_WIN_START)
        assert result is None

    def test_enroll_does_not_raise_when_db_add_raises(self):
        db = _make_db()
        db.add.side_effect = RuntimeError("simulated DB failure")
        try:
            _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                          window_start=_WIN_START)
        except Exception as exc:
            pytest.fail(f"enroll() raised unexpectedly: {exc}")

    def test_enroll_returns_none_when_commit_raises(self):
        db = _make_db(interpretation=_make_interpretation())
        db.commit.side_effect = RuntimeError("simulated commit failure")
        result = _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                               window_start=_WIN_START)
        assert result is None

    def test_evaluate_returns_zero_when_query_raises(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("simulated query failure")
        count = _svc().evaluate_ready_outcomes(db)
        assert count == 0

    def test_evaluate_does_not_raise_when_query_raises(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("simulated query failure")
        try:
            _svc().evaluate_ready_outcomes(db)
        except Exception as exc:
            pytest.fail(f"evaluate_ready_outcomes() raised unexpectedly: {exc}")

    def test_evaluate_continues_after_per_record_failure(self):
        """A failure on record 2 must not prevent record 3 from being evaluated."""
        record1 = _make_pending_record(cbm_id=1, before_last_activity_days=18)
        record2 = _make_pending_record(cbm_id=2, before_last_activity_days=18)
        record3 = _make_pending_record(cbm_id=3, before_last_activity_days=18)

        td = _make_trigger_data(activity_days=5)
        db = _make_db(pending_records=[record1, record2, record3], trigger_data=td)

        commit_call_count = [0]
        def commit_with_failure():
            commit_call_count[0] += 1
            if commit_call_count[0] == 2:
                raise RuntimeError("simulated failure on record 2")
        db.commit.side_effect = commit_with_failure

        count = _svc().evaluate_ready_outcomes(db)
        # record1 and record3 succeed; record2 fails — count is 2
        assert count == 2
        assert record1.outcome == "improved"
        assert record3.outcome == "improved"

    def test_enroll_rollback_called_on_error(self):
        db = _make_db()
        db.add.side_effect = RuntimeError("boom")
        _svc().enroll(db, cbm_id=1, user_id=42, delivery_succeeded=True,
                      window_start=_WIN_START)
        db.rollback.assert_called()
