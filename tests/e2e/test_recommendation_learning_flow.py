"""End-to-end flow test for the Recommendation Learning pipeline.

Validates the full lifecycle in execution order:
  1. record()      → creates an AI_ChatBot_Recommendations row
  2. record()      → idempotent; no duplicate inserted for same (cbm_id, recommendation_key)
  3. invalidate()  → sets is_active=False, invalidated_at, invalidation_reason
  4. get_success_rates() → aggregates total_eligible / total_improved / success_rate
                           from the JOIN with AI_ChatBot_InterventionOutcomes
  5. get_ranked_keys()   → ranks keys by success_rate descending
  6. get_ranked_keys()   → insufficient-sample keys are never dropped from the output

Prerequisites
─────────────
  MSSQL_DATABASE_URL must be set.
  alembic upgrade head must have been run so both
  AI_ChatBot_Recommendations and AI_ChatBot_InterventionOutcomes exist.

All tests skip cleanly when the URL is absent — safe for local dev.

Test isolation
──────────────
Each test inserts its own rows and removes them inside a finally block so
cleanup happens even on assertion failure.  Sentinel values use an "e2e_rec_"
prefix that does not overlap with production recommendation keys.
"""

import os
from datetime import datetime, timedelta

import pytest

from config.database import SessionLocal
from services.models import InterventionOutcome, Recommendation, TriggeredUser
from services.recommendation_learning_service import RecommendationLearningService
from services.recommendation_tracking_service import RecommendationTrackingService

_DB_URL = os.environ.get("MSSQL_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not _DB_URL,
    reason="MSSQL_DATABASE_URL not set — skipping Recommendation Learning E2E",
)

# ---------------------------------------------------------------------------
# Sentinel constants
# ---------------------------------------------------------------------------

_TEST_ENTITY_ID  = "e2e_rec_test_entity"
_TEST_REC_TYPE   = "e2e_reach_out"
_TEST_REC_KEY_A  = "e2e_rec_attendance_outreach"
_TEST_REC_KEY_B  = "e2e_rec_homework_outreach"
_TEST_REC_KEY_C  = "e2e_rec_engagement_outreach"
_TEST_DIMENSION  = "e2e_rec_test_dimension"
_TEST_RISK_LEVEL = "high"

_TEST_CONTEXT = {
    "trigger_type":  "e2e_reach_out",
    "trigger_level": "High",
    "kpi":           "attendance",
    "severity":      3,
}

# ---------------------------------------------------------------------------
# Helpers — TriggeredUser
# ---------------------------------------------------------------------------

def _insert_triggered_user() -> int:
    """Insert a minimal TriggeredUser row; return its auto-generated CBM_ID."""
    with SessionLocal() as session:
        row = TriggeredUser(
            CB_ID        = None,
            UserID       = None,
            TriggerType  = "e2e_rec_test",
            TriggerLevel = "High",
            KPI          = None,
            Severity     = None,
            InsertDate   = datetime.utcnow(),
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


# ---------------------------------------------------------------------------
# Helpers — Recommendation
# ---------------------------------------------------------------------------

def _record(cbm_id: int, key: str) -> Recommendation | None:
    """Call RecommendationTrackingService.record() and return a detached snapshot."""
    with SessionLocal() as session:
        result = RecommendationTrackingService().record(
            db                     = session,
            cbm_id                 = cbm_id,
            interpretation_id      = None,
            entity_id              = _TEST_ENTITY_ID,
            recommendation_type    = _TEST_REC_TYPE,
            recommendation_key     = key,
            recommendation_text    = f"E2E test recommendation for {key}",
            dimension              = _TEST_DIMENSION,
            risk_level             = _TEST_RISK_LEVEL,
            confidence             = 1.0,
            recommendation_context = _TEST_CONTEXT,
            generated_by           = "E2ETest",
        )
        if result is not None:
            session.expunge(result)
        return result


def _invalidate(cbm_id: int, key: str, reason: str) -> None:
    with SessionLocal() as session:
        RecommendationTrackingService().invalidate(
            db                 = session,
            cbm_id             = cbm_id,
            recommendation_key = key,
            reason             = reason,
        )


def _read_recommendation(cbm_id: int, key: str) -> Recommendation | None:
    """Return a detached Recommendation snapshot regardless of is_active value."""
    with SessionLocal() as session:
        row = (
            session.query(Recommendation)
            .filter(
                Recommendation.cbm_id == cbm_id,
                Recommendation.recommendation_key == key,
            )
            .first()
        )
        if row is None:
            return None
        session.expunge(row)
        return row


def _count_recommendations(cbm_id: int, key: str) -> int:
    with SessionLocal() as session:
        return (
            session.query(Recommendation)
            .filter(
                Recommendation.cbm_id == cbm_id,
                Recommendation.recommendation_key == key,
            )
            .count()
        )


def _delete_recommendations(cbm_id: int) -> None:
    with SessionLocal() as session:
        session.query(Recommendation).filter(
            Recommendation.cbm_id == cbm_id
        ).delete(synchronize_session=False)
        session.commit()


# ---------------------------------------------------------------------------
# Helpers — InterventionOutcome
# ---------------------------------------------------------------------------

def _insert_outcome(
    cbm_id: int,
    *,
    outcome: str,
    eligible_for_learning: bool,
) -> None:
    """Insert an InterventionOutcome row directly — bypasses the enrollment service
    so tests can control outcome and eligibility without running the full pipeline.

    Uses ORM insert (not raw SQL) because InterventionOutcome.id is a true
    IDENTITY column in SQL Server — no SET IDENTITY_INSERT issue arises since
    we do not supply an explicit id value.
    """
    with SessionLocal() as session:
        now = datetime.utcnow()
        row = InterventionOutcome(
            cbm_id                    = cbm_id,
            user_id                   = None,
            interpretation_id         = None,
            window_start              = now - timedelta(days=15),
            window_end                = now - timedelta(days=1),
            evaluation_window_days    = 14,
            delivery_gate_passed      = True,
            before_last_activity_days = 20,
            before_risk_level         = "high",
            before_snapshot_source    = "trigger_data",
            after_last_activity_days  = 10 if outcome == "improved" else 20,
            after_risk_level          = "low" if outcome == "improved" else "high",
            after_captured_at         = now,
            outcome                   = outcome,
            outcome_reason            = f"E2E test — {outcome}",
            eligible_for_learning     = eligible_for_learning,
            evaluated_at              = now,
        )
        session.add(row)
        session.commit()


def _delete_outcome(cbm_id: int) -> None:
    with SessionLocal() as session:
        session.query(InterventionOutcome).filter(
            InterventionOutcome.cbm_id == cbm_id
        ).delete(synchronize_session=False)
        session.commit()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestRecommendationLearningFlow:
    """Full lifecycle E2E: record → idempotency → invalidate → success_rates → ranking."""

    # -----------------------------------------------------------------------
    # Tracking — record()
    # -----------------------------------------------------------------------

    def test_record_creates_recommendation_row(self):
        """record() must insert one Recommendation row with the expected field values."""
        cbm_id = _insert_triggered_user()
        try:
            result = _record(cbm_id, _TEST_REC_KEY_A)

            assert result is not None,                            "record() must return a Recommendation"
            assert result.cbm_id             == cbm_id,          "cbm_id must match the trigger"
            assert result.recommendation_key == _TEST_REC_KEY_A, "recommendation_key must be stored"
            assert result.is_active          is True,            "new row must be active"
            assert result.entity_id          == _TEST_ENTITY_ID, "entity_id must be stored"
            assert result.dimension          == _TEST_DIMENSION,  "dimension must be stored"
            assert result.risk_level         == _TEST_RISK_LEVEL, "risk_level must be stored"
            assert result.confidence         == 1.0,              "confidence must be stored"
            assert result.generated_by       == "E2ETest",        "generated_by must be stored"
        finally:
            _delete_recommendations(cbm_id)
            _delete_triggered_user(cbm_id)

    def test_record_is_idempotent(self):
        """A second record() call with the same (cbm_id, recommendation_key) must
        return the existing active row without inserting a duplicate.
        """
        cbm_id = _insert_triggered_user()
        try:
            first  = _record(cbm_id, _TEST_REC_KEY_A)
            second = _record(cbm_id, _TEST_REC_KEY_A)

            assert first  is not None
            assert second is not None
            assert first.id == second.id, (
                "Idempotent record() must return the same row, not a new one"
            )
            assert _count_recommendations(cbm_id, _TEST_REC_KEY_A) == 1, (
                "Idempotent record() must not insert a duplicate row"
            )
        finally:
            _delete_recommendations(cbm_id)
            _delete_triggered_user(cbm_id)

    # -----------------------------------------------------------------------
    # Tracking — invalidate()
    # -----------------------------------------------------------------------

    def test_invalidate_sets_is_active_false(self):
        """invalidate() must set is_active=False, stamp invalidated_at, and
        store the invalidation_reason.
        """
        cbm_id = _insert_triggered_user()
        try:
            _record(cbm_id, _TEST_REC_KEY_A)
            _invalidate(cbm_id, _TEST_REC_KEY_A, "e2e_test_invalidation_reason")

            row = _read_recommendation(cbm_id, _TEST_REC_KEY_A)
            assert row is not None
            assert row.is_active          is False,                    "is_active must be False after invalidate()"
            assert row.invalidated_at     is not None,                 "invalidated_at must be stamped"
            assert row.invalidation_reason == "e2e_test_invalidation_reason", (
                "invalidation_reason must match the value passed to invalidate()"
            )
        finally:
            _delete_recommendations(cbm_id)
            _delete_triggered_user(cbm_id)

    # -----------------------------------------------------------------------
    # Learning — get_success_rates()
    # -----------------------------------------------------------------------

    def test_get_success_rates_calculates_correctly(self):
        """get_success_rates() must JOIN AI_ChatBot_Recommendations to
        AI_ChatBot_InterventionOutcomes on cbm_id and correctly compute
        total_eligible, total_improved, and success_rate.

        Setup:
          cbm_a → key_A recommendation + outcome='improved',     eligible=True
          cbm_b → key_A recommendation + outcome='not_improved', eligible=True
          Expected for key_A: total_eligible=2, total_improved=1, success_rate=0.5
        """
        cbm_a = _insert_triggered_user()
        cbm_b = _insert_triggered_user()
        try:
            _record(cbm_a, _TEST_REC_KEY_A)
            _record(cbm_b, _TEST_REC_KEY_A)
            _insert_outcome(cbm_a, outcome="improved",     eligible_for_learning=True)
            _insert_outcome(cbm_b, outcome="not_improved", eligible_for_learning=True)

            with SessionLocal() as session:
                rates = RecommendationLearningService().get_success_rates(
                    session,
                    dimension=_TEST_DIMENSION,
                )

            key_a_entries = [r for r in rates if r["recommendation_key"] == _TEST_REC_KEY_A]
            assert len(key_a_entries) == 1, (
                f"Expected exactly one rate entry for {_TEST_REC_KEY_A!r}; got {len(key_a_entries)}"
            )

            entry = key_a_entries[0]
            assert entry["total_eligible"] == 2, (
                f"total_eligible must be 2; got {entry['total_eligible']}"
            )
            assert entry["total_improved"] == 1, (
                f"total_improved must be 1; got {entry['total_improved']}"
            )
            assert abs(entry["success_rate"] - 0.5) < 1e-9, (
                f"success_rate must be 0.5; got {entry['success_rate']}"
            )
        finally:
            _delete_outcome(cbm_a)
            _delete_outcome(cbm_b)
            _delete_recommendations(cbm_a)
            _delete_recommendations(cbm_b)
            _delete_triggered_user(cbm_a)
            _delete_triggered_user(cbm_b)

    # -----------------------------------------------------------------------
    # Learning — get_ranked_keys()
    # -----------------------------------------------------------------------

    def test_get_ranked_keys_ranks_by_success_rate_descending(self):
        """get_ranked_keys() must place the key with the higher success_rate first.

        Setup (min_sample=2 — both keys have sufficient sample):
          key_A: 2 eligible, 2 improved  → success_rate=1.0
          key_B: 2 eligible, 0 improved  → success_rate=0.0
          Expected: [key_A, key_B]
        """
        cbm_a1 = _insert_triggered_user()
        cbm_a2 = _insert_triggered_user()
        cbm_b1 = _insert_triggered_user()
        cbm_b2 = _insert_triggered_user()
        try:
            _record(cbm_a1, _TEST_REC_KEY_A)
            _record(cbm_a2, _TEST_REC_KEY_A)
            _record(cbm_b1, _TEST_REC_KEY_B)
            _record(cbm_b2, _TEST_REC_KEY_B)

            _insert_outcome(cbm_a1, outcome="improved",     eligible_for_learning=True)
            _insert_outcome(cbm_a2, outcome="improved",     eligible_for_learning=True)
            _insert_outcome(cbm_b1, outcome="not_improved", eligible_for_learning=True)
            _insert_outcome(cbm_b2, outcome="not_improved", eligible_for_learning=True)

            with SessionLocal() as session:
                ranked = RecommendationLearningService().get_ranked_keys(
                    session,
                    [_TEST_REC_KEY_A, _TEST_REC_KEY_B],
                    dimension  = _TEST_DIMENSION,
                    min_sample = 2,
                )

            assert len(ranked) == 2, f"Both candidates must be present; got {ranked}"
            assert ranked[0] == _TEST_REC_KEY_A, (
                f"key_A (rate=1.0) must rank before key_B (rate=0.0); got {ranked}"
            )
            assert ranked[1] == _TEST_REC_KEY_B
        finally:
            for cbm_id in (cbm_a1, cbm_a2, cbm_b1, cbm_b2):
                _delete_outcome(cbm_id)
                _delete_recommendations(cbm_id)
                _delete_triggered_user(cbm_id)

    def test_insufficient_sample_keys_remain_in_output(self):
        """A key below min_sample must still appear in get_ranked_keys() output.

        No candidates are ever dropped — insufficient-sample keys are appended
        after the ranked group in their original candidate order.

        Setup (min_sample=2):
          key_A: 2 eligible, 1 improved  → rate=0.5 (sufficient) → ranked
          key_C: 1 eligible, 1 improved  → total_eligible=1 < 2   → insufficient, appended
          Expected: both present; key_A before key_C
        """
        cbm_a1 = _insert_triggered_user()
        cbm_a2 = _insert_triggered_user()
        cbm_c  = _insert_triggered_user()
        try:
            _record(cbm_a1, _TEST_REC_KEY_A)
            _record(cbm_a2, _TEST_REC_KEY_A)
            _record(cbm_c,  _TEST_REC_KEY_C)

            _insert_outcome(cbm_a1, outcome="improved",     eligible_for_learning=True)
            _insert_outcome(cbm_a2, outcome="not_improved", eligible_for_learning=True)
            _insert_outcome(cbm_c,  outcome="improved",     eligible_for_learning=True)

            with SessionLocal() as session:
                ranked = RecommendationLearningService().get_ranked_keys(
                    session,
                    [_TEST_REC_KEY_A, _TEST_REC_KEY_C],
                    dimension  = _TEST_DIMENSION,
                    min_sample = 2,
                )

            assert _TEST_REC_KEY_A in ranked, f"key_A must be in the output; got {ranked}"
            assert _TEST_REC_KEY_C in ranked, (
                f"key_C (insufficient sample) must never be dropped; got {ranked}"
            )
            assert ranked.index(_TEST_REC_KEY_A) < ranked.index(_TEST_REC_KEY_C), (
                f"Ranked key_A must precede unranked key_C; got {ranked}"
            )
        finally:
            for cbm_id in (cbm_a1, cbm_a2, cbm_c):
                _delete_outcome(cbm_id)
                _delete_recommendations(cbm_id)
                _delete_triggered_user(cbm_id)

    # -----------------------------------------------------------------------
    # Cleanup meta-test
    # -----------------------------------------------------------------------

    def test_cleanup_removes_all_inserted_test_rows(self):
        """Verify the cleanup helpers used by every test work correctly.

        This is a meta-test: if the helpers are broken, all other tests silently
        leave orphan rows in the DB.
        """
        cbm_id = _insert_triggered_user()
        _record(cbm_id, _TEST_REC_KEY_A)
        _insert_outcome(cbm_id, outcome="improved", eligible_for_learning=True)

        _delete_outcome(cbm_id)
        _delete_recommendations(cbm_id)
        _delete_triggered_user(cbm_id)

        assert _read_recommendation(cbm_id, _TEST_REC_KEY_A) is None, (
            "Recommendation row must be removed by _delete_recommendations()"
        )
        assert _count_recommendations(cbm_id, _TEST_REC_KEY_A) == 0, (
            "No Recommendation rows must remain after cleanup"
        )
        with SessionLocal() as session:
            assert session.get(TriggeredUser, cbm_id) is None, (
                "TriggeredUser row must be removed by _delete_triggered_user()"
            )
            assert (
                session.query(InterventionOutcome)
                .filter(InterventionOutcome.cbm_id == cbm_id)
                .first()
            ) is None, "InterventionOutcome row must be removed by _delete_outcome()"
