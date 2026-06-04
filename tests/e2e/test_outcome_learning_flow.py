"""End-to-end flow test for the Intervention Outcome learning pipeline.

Validates the full lifecycle in execution order:
  1. enroll()                  → creates an InterventionOutcome row with outcome='pending'
  2. evaluate_ready_outcomes() → transitions the row to a final outcome label
  3. All outcome fields are correctly set:
       outcome, evaluated_at, eligible_for_learning,
       before_last_activity_days, after_last_activity_days

Prerequisites
─────────────
  MSSQL_DATABASE_URL must be set.
  alembic upgrade head must have been run so AI_ChatBot_InterventionOutcomes
  exists in the target database.

All tests skip cleanly when the URL is absent — safe for local dev.

Test isolation
──────────────
Each test inserts its own rows and removes them inside a finally block so
cleanup happens even on assertion failure.  Sentinel UserID 8888888 is used
for TriggerData; it must not collide with real student records.
"""

import os
from datetime import datetime, timedelta

import pytest

from sqlalchemy import text

from config.database import SessionLocal
from services.intervention_outcome_service import InterventionOutcomeService
from services.models import InterventionOutcome, TriggerData, TriggeredUser

_DB_URL = os.environ.get("MSSQL_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not _DB_URL,
    reason="MSSQL_DATABASE_URL not set — skipping Outcome Learning E2E",
)

# ---------------------------------------------------------------------------
# Sentinel constants
# ---------------------------------------------------------------------------

# Deliberately large value unlikely to match any real student's UserID.
# Used as the primary key for the TriggerData row inserted by these tests.
_TEST_USER_ID = 8_888_888

# window_start 15 days ago + 14-day window → window_end is yesterday → immediately evaluable.
_PAST_START  = datetime.utcnow() - timedelta(days=15)
_WINDOW_DAYS = 14

# ---------------------------------------------------------------------------
# Insert / read / delete helpers
# ---------------------------------------------------------------------------

def _insert_triggered_user(user_id=None) -> int:
    """Insert a minimal TriggeredUser and return its CBM_ID."""
    with SessionLocal() as session:
        row = TriggeredUser(
            CB_ID        = None,
            UserID       = user_id,
            TriggerType  = "e2e_outcome_test",
            TriggerLevel = "Low",
            KPI          = None,
            Severity     = None,
            InsertDate   = _PAST_START,
            Completed    = 1,
            AgentID      = None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.CBM_ID


def _delete_triggered_user(cbm_id: int) -> None:
    with SessionLocal() as session:
        row = session.get(TriggeredUser, cbm_id)
        if row is not None:
            session.delete(row)
            session.commit()


def _insert_trigger_data(last_activity_days: int) -> None:
    """Insert a minimal TriggerData row for the sentinel user.

    Uses raw SQL to avoid SQLAlchemy's MSSQL IDENTITY_INSERT mechanism.
    AI_ChatBot_TriggerData.UserID is not an identity column in SQL Server,
    so the ORM path incorrectly issues SET IDENTITY_INSERT ON and fails.
    """
    with SessionLocal() as session:
        session.execute(
            text(
                "INSERT INTO AI_ChatBot_TriggerData"
                " (UserID, UserName, FirstName, LastName, LastActivityDays,"
                "  GroupStatus, ChatGPT_prompt, DataDictionary)"
                " VALUES (:uid, :uname, :first, :last, :lad,"
                "  :group_status, :chatgpt_prompt, :data_dictionary)"
            ),
            {
                "uid":              _TEST_USER_ID,
                "uname":            f"e2e_test_{_TEST_USER_ID}",
                "first":            "E2ETest",
                "last":             "Sentinel",
                "lad":              last_activity_days,
                "group_status":     "ACTIVE",
                "chatgpt_prompt":   "E2E Test Prompt",
                "data_dictionary":  "E2E Test Dictionary",
            },
        )
        session.commit()


def _update_trigger_data_activity(last_activity_days: int) -> None:
    """Update LastActivityDays on the sentinel TriggerData row."""
    with SessionLocal() as session:
        row = session.get(TriggerData, _TEST_USER_ID)
        if row is not None:
            row.LastActivityDays = last_activity_days
            session.commit()


def _delete_trigger_data() -> None:
    with SessionLocal() as session:
        row = session.get(TriggerData, _TEST_USER_ID)
        if row is not None:
            session.delete(row)
            session.commit()


def _delete_outcome(cbm_id: int) -> None:
    with SessionLocal() as session:
        row = (
            session.query(InterventionOutcome)
            .filter(InterventionOutcome.cbm_id == cbm_id)
            .first()
        )
        if row is not None:
            session.delete(row)
            session.commit()


def _read_outcome(cbm_id: int):
    """Return a detached InterventionOutcome snapshot (all columns pre-loaded)."""
    with SessionLocal() as session:
        row = (
            session.query(InterventionOutcome)
            .filter(InterventionOutcome.cbm_id == cbm_id)
            .first()
        )
        if row is None:
            return None
        # Force-load all columns before the session closes.
        session.expunge(row)
        return row


def _enroll(cbm_id: int, user_id, delivery_succeeded):
    with SessionLocal() as session:
        record = InterventionOutcomeService().enroll(
            db                 = session,
            cbm_id             = cbm_id,
            user_id            = user_id,
            delivery_succeeded = delivery_succeeded,
            window_start       = _PAST_START,
            evaluation_window_days = _WINDOW_DAYS,
        )
        if record is not None:
            session.expunge(record)
        return record


def _evaluate() -> int:
    with SessionLocal() as session:
        return InterventionOutcomeService().evaluate_ready_outcomes(session)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestOutcomeLearningFlow:
    """Full lifecycle E2E: enrollment → pending → evaluation → final outcome."""

    # -----------------------------------------------------------------------
    # Enrollment state
    # -----------------------------------------------------------------------

    def test_enrollment_creates_pending_record(self):
        """enroll() must create one InterventionOutcome row with outcome='pending'
        and NULL evaluated_at / eligible_for_learning.
        """
        cbm_id = _insert_triggered_user(user_id=None)
        try:
            record = _enroll(cbm_id, user_id=None, delivery_succeeded=True)

            assert record is not None,                    "enroll() must return the new record"
            assert record.cbm_id     == cbm_id,           "cbm_id must match the trigger"
            assert record.outcome    == "pending",         "outcome must be 'pending' at enrollment"
            assert record.evaluated_at         is None,   "evaluated_at must be NULL at enrollment"
            assert record.eligible_for_learning is None,  "eligible must be NULL at enrollment"
            assert record.window_end > record.window_start
        finally:
            _delete_outcome(cbm_id)
            _delete_triggered_user(cbm_id)

    def test_enrollment_is_idempotent(self):
        """A second enroll() call for the same cbm_id must return the existing
        record without inserting a duplicate row.
        """
        cbm_id = _insert_triggered_user(user_id=None)
        try:
            first  = _enroll(cbm_id, user_id=None, delivery_succeeded=True)
            second = _enroll(cbm_id, user_id=None, delivery_succeeded=True)

            assert first  is not None
            assert second is not None
            assert first.id == second.id, "Duplicate enroll must return the same row"

            with SessionLocal() as session:
                count = (
                    session.query(InterventionOutcome)
                    .filter(InterventionOutcome.cbm_id == cbm_id)
                    .count()
                )
            assert count == 1, "Idempotent enroll must not insert a duplicate row"
        finally:
            _delete_outcome(cbm_id)
            _delete_triggered_user(cbm_id)

    # -----------------------------------------------------------------------
    # Inconclusive outcomes
    # -----------------------------------------------------------------------

    def test_inconclusive_when_delivery_gate_failed(self):
        """delivery_succeeded=False → outcome='inconclusive', eligible_for_learning=False."""
        cbm_id = _insert_triggered_user(user_id=None)
        try:
            _enroll(cbm_id, user_id=None, delivery_succeeded=False)
            evaluated = _evaluate()

            assert evaluated >= 1

            record = _read_outcome(cbm_id)
            assert record is not None
            assert record.outcome               == "inconclusive"
            assert record.eligible_for_learning is False
            assert record.evaluated_at          is not None
        finally:
            _delete_outcome(cbm_id)
            _delete_triggered_user(cbm_id)

    def test_inconclusive_when_no_before_state(self):
        """user_id=None → before-state unavailable → inconclusive even with delivery gate passed."""
        cbm_id = _insert_triggered_user(user_id=None)
        try:
            _enroll(cbm_id, user_id=None, delivery_succeeded=True)
            _evaluate()

            record = _read_outcome(cbm_id)
            assert record is not None
            assert record.outcome               == "inconclusive"
            assert record.eligible_for_learning is False
            assert record.before_snapshot_source == "unavailable"
        finally:
            _delete_outcome(cbm_id)
            _delete_triggered_user(cbm_id)

    def test_inconclusive_when_student_already_healthy(self):
        """before_last_activity_days=2 ≤ 3 (healthy threshold) → inconclusive."""
        cbm_id = _insert_triggered_user(user_id=_TEST_USER_ID)
        _insert_trigger_data(last_activity_days=2)
        try:
            _enroll(cbm_id, user_id=_TEST_USER_ID, delivery_succeeded=True)
            _evaluate()

            record = _read_outcome(cbm_id)
            assert record is not None
            assert record.outcome               == "inconclusive"
            assert record.eligible_for_learning is False
            assert record.before_last_activity_days == 2
        finally:
            _delete_outcome(cbm_id)
            _delete_triggered_user(cbm_id)
            _delete_trigger_data()

    # -----------------------------------------------------------------------
    # Scored outcomes
    # -----------------------------------------------------------------------

    def test_not_improved_when_delta_below_threshold(self):
        """before=20, after=20 (TriggerData unchanged) → delta=0 < 3 → not_improved.

        before_last_activity_days is captured at enrollment from TriggerData.
        after_last_activity_days  is read at evaluation from the same row.
        When the row is not updated between the two calls, delta=0 → not_improved.
        """
        cbm_id = _insert_triggered_user(user_id=_TEST_USER_ID)
        _insert_trigger_data(last_activity_days=20)
        try:
            _enroll(cbm_id, user_id=_TEST_USER_ID, delivery_succeeded=True)
            _evaluate()

            record = _read_outcome(cbm_id)
            assert record is not None
            assert record.outcome                   == "not_improved"
            assert record.eligible_for_learning     is True
            assert record.evaluated_at              is not None
            assert record.before_last_activity_days == 20
            assert record.after_last_activity_days  == 20
        finally:
            _delete_outcome(cbm_id)
            _delete_triggered_user(cbm_id)
            _delete_trigger_data()

    def test_improved_when_delta_meets_threshold(self):
        """before=20 (at enrollment), after=10 (updated before evaluation) → delta=10 ≥ 3 → improved.

        Simulates a student whose activity days decreased between the intervention
        and the evaluation window close.
        """
        cbm_id = _insert_triggered_user(user_id=_TEST_USER_ID)
        _insert_trigger_data(last_activity_days=20)
        try:
            _enroll(cbm_id, user_id=_TEST_USER_ID, delivery_succeeded=True)

            # Simulate student activity improvement before window closes
            _update_trigger_data_activity(last_activity_days=10)

            _evaluate()

            record = _read_outcome(cbm_id)
            assert record is not None
            assert record.outcome                   == "improved"
            assert record.eligible_for_learning     is True
            assert record.evaluated_at              is not None
            assert record.before_last_activity_days == 20
            assert record.after_last_activity_days  == 10
        finally:
            _delete_outcome(cbm_id)
            _delete_triggered_user(cbm_id)
            _delete_trigger_data()

    # -----------------------------------------------------------------------
    # Field-level assertions
    # -----------------------------------------------------------------------

    def test_evaluated_at_is_set_and_not_before_evaluation_run(self):
        """evaluated_at must be a datetime stamped at or after the evaluation call."""
        cbm_id = _insert_triggered_user(user_id=None)
        try:
            _enroll(cbm_id, user_id=None, delivery_succeeded=False)
            before_eval = datetime.utcnow()
            _evaluate()

            record = _read_outcome(cbm_id)
            assert record.evaluated_at is not None
            assert record.evaluated_at >= before_eval - timedelta(milliseconds=10), (
                "evaluated_at must not predate the evaluation run by more than "
                "SQL Server DATETIME precision (~3.33 ms)"
            )
        finally:
            _delete_outcome(cbm_id)
            _delete_triggered_user(cbm_id)

    def test_eligible_for_learning_false_for_all_inconclusive_variants(self):
        """eligible_for_learning must be False for every inconclusive outcome."""
        cbm_ids = []
        try:
            # Variant 1: delivery gate
            cid1 = _insert_triggered_user(user_id=None)
            cbm_ids.append(cid1)
            _enroll(cid1, user_id=None, delivery_succeeded=False)

            # Variant 2: no before-state
            cid2 = _insert_triggered_user(user_id=None)
            cbm_ids.append(cid2)
            _enroll(cid2, user_id=None, delivery_succeeded=True)

            _evaluate()

            for cbm_id in cbm_ids:
                record = _read_outcome(cbm_id)
                assert record is not None
                assert record.eligible_for_learning is False, (
                    f"cbm_id={cbm_id}: inconclusive outcome must have eligible=False"
                )
        finally:
            for cbm_id in cbm_ids:
                _delete_outcome(cbm_id)
                _delete_triggered_user(cbm_id)

    def test_eligible_for_learning_true_for_scored_outcomes(self):
        """eligible_for_learning must be True for improved and not_improved outcomes."""
        cbm_id = _insert_triggered_user(user_id=_TEST_USER_ID)
        _insert_trigger_data(last_activity_days=20)
        try:
            _enroll(cbm_id, user_id=_TEST_USER_ID, delivery_succeeded=True)
            _evaluate()

            record = _read_outcome(cbm_id)
            assert record is not None
            assert record.outcome in ("improved", "not_improved")
            assert record.eligible_for_learning is True
        finally:
            _delete_outcome(cbm_id)
            _delete_triggered_user(cbm_id)
            _delete_trigger_data()

    # -----------------------------------------------------------------------
    # Cleanup meta-test
    # -----------------------------------------------------------------------

    def test_cleanup_removes_all_inserted_test_rows(self):
        """Verify the cleanup helpers used by every test work correctly.

        This is a meta-test: if the helpers are broken, all other tests silently
        leave orphan rows in the DB.
        """
        cbm_id = _insert_triggered_user(user_id=_TEST_USER_ID)
        _insert_trigger_data(last_activity_days=15)
        _enroll(cbm_id, user_id=_TEST_USER_ID, delivery_succeeded=True)

        # Run cleanup
        _delete_outcome(cbm_id)
        _delete_triggered_user(cbm_id)
        _delete_trigger_data()

        # Assert all rows are gone
        assert _read_outcome(cbm_id) is None, \
            "InterventionOutcome row must be removed by _delete_outcome()"

        with SessionLocal() as session:
            assert session.get(TriggeredUser, cbm_id) is None, \
                "TriggeredUser row must be removed by _delete_triggered_user()"
            assert session.get(TriggerData, _TEST_USER_ID) is None, \
                "TriggerData row must be removed by _delete_trigger_data()"
