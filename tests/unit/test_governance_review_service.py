"""Unit tests for GovernanceReviewService.

All tests are isolated — no real database session, no network.
The db session is a MagicMock that simulates query/filter/commit/refresh chains.
GovernanceReview objects are built as SimpleNamespace stubs.

Test categories:
  - create_pending_review: shape, status, field values, DB write verification
  - approve_review: status transition, reviewer fields, optional notes
  - reject_review: status transition, notes required, empty-notes rejection
  - defer_review: status transition, reason required, empty-reason rejection
  - get_pending_reviews: basic retrieval, entity_type filter, risk_level filter
  - get_review_history: retrieval, ordering by created_at
  - _load_or_raise: not-found raises ValueError
  - audit_snapshot_json serialization
  - Orchestration integration: governance review auto-created when generate_new fires
  - GovernanceReviewStatus enum completeness
  - Pydantic schema: valid data, required-field enforcement, ORM round-trip
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from pydantic import ValidationError

from services.governance_review_service import GovernanceReviewService
from services.models import GovernanceReview, GovernanceReviewStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SVC = GovernanceReviewService()

_ENTITY_ID    = "101"
_ENTITY_TYPE  = "student"
_INTERP_ID    = 42
_RISK_LEVEL   = "high"
_CONFIDENCE   = 0.88
_REASON       = "Risk escalation detected: prior_risk='low' → current='high'."


def _make_db(review: "SimpleNamespace | None" = None) -> MagicMock:
    """Mock session whose .query().filter().first() returns `review`."""
    db = MagicMock()
    q  = MagicMock()
    q.filter.return_value     = q
    q.order_by.return_value   = q
    q.limit.return_value      = q
    q.first.return_value      = review
    q.all.return_value        = [review] if review is not None else []
    db.query.return_value     = q
    db.refresh.side_effect    = lambda obj: setattr(obj, "id", 77)
    return db


def _stub_review(
    id_val: int = 77,
    status: str = "pending",
    risk_level: str = _RISK_LEVEL,
    confidence: float = _CONFIDENCE,
    reviewed_by: str | None = None,
    reviewed_at: datetime | None = None,
    review_notes: str | None = None,
    governance_reason: str = _REASON,
    audit_snapshot_json: str | None = None,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id                  = id_val,
        interpretation_id   = _INTERP_ID,
        entity_id           = _ENTITY_ID,
        entity_type         = _ENTITY_TYPE,
        status              = status,
        risk_level          = risk_level,
        confidence          = confidence,
        reviewed_by         = reviewed_by,
        reviewed_at         = reviewed_at,
        review_notes        = review_notes,
        governance_reason   = governance_reason,
        audit_snapshot_json = audit_snapshot_json,
        is_active           = is_active,
        created_at          = datetime(2026, 1, 1),
        updated_at          = datetime(2026, 1, 1),
    )


# ===========================================================================
# GovernanceReviewStatus enum
# ===========================================================================

class TestGovernanceReviewStatusEnum:
    def test_has_all_four_values(self):
        values = {s.value for s in GovernanceReviewStatus}
        assert values == {"pending", "approved", "rejected", "deferred"}

    def test_is_string_subtype(self):
        assert isinstance(GovernanceReviewStatus.pending, str)

    def test_pending_value(self):
        assert GovernanceReviewStatus.pending == "pending"

    def test_approved_value(self):
        assert GovernanceReviewStatus.approved == "approved"

    def test_rejected_value(self):
        assert GovernanceReviewStatus.rejected == "rejected"

    def test_deferred_value(self):
        assert GovernanceReviewStatus.deferred == "deferred"


# ===========================================================================
# GovernanceReview ORM column defaults
# ===========================================================================

class TestGovernanceReviewModel:
    def test_status_column_default_is_pending(self):
        col = GovernanceReview.__table__.c.status
        assert col.default.arg == "pending"

    def test_is_active_column_default_is_true(self):
        col = GovernanceReview.__table__.c.is_active
        assert col.default.arg is True

    def test_reviewed_by_is_nullable(self):
        assert GovernanceReview.__table__.c.reviewed_by.nullable is True

    def test_reviewed_at_is_nullable(self):
        assert GovernanceReview.__table__.c.reviewed_at.nullable is True

    def test_review_notes_is_nullable(self):
        assert GovernanceReview.__table__.c.review_notes.nullable is True

    def test_audit_snapshot_json_is_nullable(self):
        assert GovernanceReview.__table__.c.audit_snapshot_json.nullable is True

    def test_governance_reason_is_not_nullable(self):
        assert GovernanceReview.__table__.c.governance_reason.nullable is False

    def test_risk_level_is_not_nullable(self):
        assert GovernanceReview.__table__.c.risk_level.nullable is False


# ===========================================================================
# create_pending_review
# ===========================================================================

class TestCreatePendingReview:
    def test_returns_governance_review_object(self):
        db = _make_db()
        result = SVC.create_pending_review(
            db, _INTERP_ID, _ENTITY_ID, _ENTITY_TYPE,
            _RISK_LEVEL, _CONFIDENCE, _REASON,
        )
        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, GovernanceReview)

    def test_status_is_pending(self):
        db = _make_db()
        SVC.create_pending_review(
            db, _INTERP_ID, _ENTITY_ID, _ENTITY_TYPE,
            _RISK_LEVEL, _CONFIDENCE, _REASON,
        )
        added = db.add.call_args[0][0]
        assert added.status == GovernanceReviewStatus.pending

    def test_entity_id_and_type_set(self):
        db = _make_db()
        SVC.create_pending_review(
            db, _INTERP_ID, _ENTITY_ID, _ENTITY_TYPE,
            _RISK_LEVEL, _CONFIDENCE, _REASON,
        )
        added = db.add.call_args[0][0]
        assert added.entity_id   == _ENTITY_ID
        assert added.entity_type == _ENTITY_TYPE

    def test_interpretation_id_set(self):
        db = _make_db()
        SVC.create_pending_review(
            db, _INTERP_ID, _ENTITY_ID, _ENTITY_TYPE,
            _RISK_LEVEL, _CONFIDENCE, _REASON,
        )
        added = db.add.call_args[0][0]
        assert added.interpretation_id == _INTERP_ID

    def test_risk_level_and_confidence_set(self):
        db = _make_db()
        SVC.create_pending_review(
            db, _INTERP_ID, _ENTITY_ID, _ENTITY_TYPE,
            _RISK_LEVEL, _CONFIDENCE, _REASON,
        )
        added = db.add.call_args[0][0]
        assert added.risk_level == _RISK_LEVEL
        assert added.confidence == pytest.approx(_CONFIDENCE)

    def test_governance_reason_set(self):
        db = _make_db()
        SVC.create_pending_review(
            db, _INTERP_ID, _ENTITY_ID, _ENTITY_TYPE,
            _RISK_LEVEL, _CONFIDENCE, _REASON,
        )
        added = db.add.call_args[0][0]
        assert added.governance_reason == _REASON

    def test_db_commit_and_refresh_called(self):
        db = _make_db()
        SVC.create_pending_review(
            db, _INTERP_ID, _ENTITY_ID, _ENTITY_TYPE,
            _RISK_LEVEL, _CONFIDENCE, _REASON,
        )
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    def test_audit_snapshot_serialized_to_json(self):
        db = _make_db()
        snapshot = {"dimension": "engagement", "risk_level": "high"}
        SVC.create_pending_review(
            db, _INTERP_ID, _ENTITY_ID, _ENTITY_TYPE,
            _RISK_LEVEL, _CONFIDENCE, _REASON,
            audit_snapshot=snapshot,
        )
        added = db.add.call_args[0][0]
        parsed = json.loads(added.audit_snapshot_json)
        assert parsed["dimension"] == "engagement"

    def test_no_audit_snapshot_stores_none(self):
        db = _make_db()
        SVC.create_pending_review(
            db, _INTERP_ID, _ENTITY_ID, _ENTITY_TYPE,
            _RISK_LEVEL, _CONFIDENCE, _REASON,
        )
        added = db.add.call_args[0][0]
        assert added.audit_snapshot_json is None


# ===========================================================================
# approve_review
# ===========================================================================

class TestApproveReview:
    def _setup(self, **kwargs):
        review = _stub_review(**kwargs)
        db = _make_db(review=review)
        return db, review

    def test_status_set_to_approved(self):
        db, review = self._setup()
        SVC.approve_review(db, review_id=77, reviewed_by="jane@example.com")
        assert review.status == GovernanceReviewStatus.approved

    def test_reviewed_by_set(self):
        db, review = self._setup()
        SVC.approve_review(db, review_id=77, reviewed_by="jane@example.com")
        assert review.reviewed_by == "jane@example.com"

    def test_reviewed_at_set_to_datetime(self):
        db, review = self._setup()
        SVC.approve_review(db, review_id=77, reviewed_by="jane@example.com")
        assert isinstance(review.reviewed_at, datetime)

    def test_optional_review_notes_set_when_provided(self):
        db, review = self._setup()
        SVC.approve_review(db, review_id=77, reviewed_by="jane@example.com",
                           review_notes="Confirmed via grade book.")
        assert review.review_notes == "Confirmed via grade book."

    def test_review_notes_unchanged_when_not_provided(self):
        db, review = self._setup(review_notes=None)
        SVC.approve_review(db, review_id=77, reviewed_by="jane@example.com")
        assert review.review_notes is None

    def test_db_add_commit_refresh_called(self):
        db, review = self._setup()
        SVC.approve_review(db, review_id=77, reviewed_by="jane@example.com")
        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    def test_raises_value_error_when_review_not_found(self):
        db = _make_db(review=None)
        with pytest.raises(ValueError, match="not found"):
            SVC.approve_review(db, review_id=999, reviewed_by="jane@example.com")


# ===========================================================================
# reject_review
# ===========================================================================

class TestRejectReview:
    def _setup(self, **kwargs):
        review = _stub_review(**kwargs)
        db = _make_db(review=review)
        return db, review

    def test_status_set_to_rejected(self):
        db, review = self._setup()
        SVC.reject_review(db, review_id=77, reviewed_by="bob@example.com",
                          review_notes="Risk level appears overstated.")
        assert review.status == GovernanceReviewStatus.rejected

    def test_reviewed_by_and_notes_set(self):
        db, review = self._setup()
        SVC.reject_review(db, review_id=77, reviewed_by="bob@example.com",
                          review_notes="Does not match observed behavior.")
        assert review.reviewed_by  == "bob@example.com"
        assert review.review_notes == "Does not match observed behavior."

    def test_reviewed_at_set_to_datetime(self):
        db, review = self._setup()
        SVC.reject_review(db, review_id=77, reviewed_by="bob@example.com",
                          review_notes="Incorrect assessment.")
        assert isinstance(review.reviewed_at, datetime)

    def test_raises_value_error_on_empty_review_notes(self):
        db, review = self._setup()
        with pytest.raises(ValueError, match="review_notes is required"):
            SVC.reject_review(db, review_id=77, reviewed_by="bob@example.com",
                              review_notes="")

    def test_raises_value_error_on_whitespace_only_notes(self):
        db, review = self._setup()
        with pytest.raises(ValueError, match="review_notes is required"):
            SVC.reject_review(db, review_id=77, reviewed_by="bob@example.com",
                              review_notes="   ")

    def test_raises_value_error_when_not_found(self):
        db = _make_db(review=None)
        with pytest.raises(ValueError, match="not found"):
            SVC.reject_review(db, review_id=999, reviewed_by="bob@example.com",
                              review_notes="Some notes.")

    def test_db_commit_called(self):
        db, review = self._setup()
        SVC.reject_review(db, review_id=77, reviewed_by="bob@example.com",
                          review_notes="Incorrect risk level.")
        db.commit.assert_called_once()


# ===========================================================================
# defer_review
# ===========================================================================

class TestDeferReview:
    def _setup(self, **kwargs):
        review = _stub_review(**kwargs)
        db = _make_db(review=review)
        return db, review

    def test_status_set_to_deferred(self):
        db, review = self._setup()
        SVC.defer_review(db, review_id=77, reviewed_by="carol@example.com",
                         governance_reason="Awaiting updated attendance data.")
        assert review.status == GovernanceReviewStatus.deferred

    def test_reviewed_by_and_governance_reason_set(self):
        db, review = self._setup()
        SVC.defer_review(db, review_id=77, reviewed_by="carol@example.com",
                         governance_reason="Need last 30 days of login history.")
        assert review.reviewed_by       == "carol@example.com"
        assert review.governance_reason == "Need last 30 days of login history."

    def test_reviewed_at_set_to_datetime(self):
        db, review = self._setup()
        SVC.defer_review(db, review_id=77, reviewed_by="carol@example.com",
                         governance_reason="Awaiting more data.")
        assert isinstance(review.reviewed_at, datetime)

    def test_raises_value_error_on_empty_governance_reason(self):
        db, review = self._setup()
        with pytest.raises(ValueError, match="governance_reason is required"):
            SVC.defer_review(db, review_id=77, reviewed_by="carol@example.com",
                             governance_reason="")

    def test_raises_value_error_on_whitespace_reason(self):
        db, review = self._setup()
        with pytest.raises(ValueError, match="governance_reason is required"):
            SVC.defer_review(db, review_id=77, reviewed_by="carol@example.com",
                             governance_reason="   ")

    def test_raises_value_error_when_not_found(self):
        db = _make_db(review=None)
        with pytest.raises(ValueError, match="not found"):
            SVC.defer_review(db, review_id=999, reviewed_by="carol@example.com",
                             governance_reason="Some reason.")

    def test_db_commit_called(self):
        db, review = self._setup()
        SVC.defer_review(db, review_id=77, reviewed_by="carol@example.com",
                         governance_reason="Awaiting data.")
        db.commit.assert_called_once()


# ===========================================================================
# get_pending_reviews
# ===========================================================================

class TestGetPendingReviews:
    def test_returns_list_from_db(self):
        review = _stub_review(status="pending")
        db = _make_db(review=review)
        results = SVC.get_pending_reviews(db)
        assert isinstance(results, list)

    def test_queries_pending_status(self):
        db = _make_db()
        SVC.get_pending_reviews(db)
        # Ensure .filter was called (status and is_active filters applied)
        db.query.return_value.filter.assert_called()

    def test_limit_hard_capped_at_500(self):
        db = _make_db()
        SVC.get_pending_reviews(db, limit=9999)
        # .limit() should have been called with 500
        db.query.return_value.filter.return_value.order_by.return_value.limit.assert_called_with(500)

    def test_default_limit_is_100(self):
        db = _make_db()
        SVC.get_pending_reviews(db)
        db.query.return_value.filter.return_value.order_by.return_value.limit.assert_called_with(100)

    def test_entity_type_filter_applied_when_provided(self):
        db = _make_db()
        SVC.get_pending_reviews(db, entity_type="student")
        # filter should be called a second time for entity_type
        assert db.query.return_value.filter.return_value.filter.called

    def test_risk_level_filter_applied_when_provided(self):
        db = _make_db()
        SVC.get_pending_reviews(db, risk_level="high")
        assert db.query.return_value.filter.return_value.filter.called


# ===========================================================================
# get_review_history
# ===========================================================================

class TestGetReviewHistory:
    def test_returns_list_from_db(self):
        review = _stub_review(status="approved")
        db = _make_db(review=review)
        results = SVC.get_review_history(db, _ENTITY_ID, _ENTITY_TYPE)
        assert isinstance(results, list)

    def test_filters_by_entity_id_and_type(self):
        db = _make_db()
        SVC.get_review_history(db, _ENTITY_ID, _ENTITY_TYPE)
        db.query.return_value.filter.assert_called()

    def test_limit_hard_capped_at_200(self):
        db = _make_db()
        SVC.get_review_history(db, _ENTITY_ID, _ENTITY_TYPE, limit=9999)
        db.query.return_value.filter.return_value.order_by.return_value.limit.assert_called_with(200)

    def test_default_limit_is_50(self):
        db = _make_db()
        SVC.get_review_history(db, _ENTITY_ID, _ENTITY_TYPE)
        db.query.return_value.filter.return_value.order_by.return_value.limit.assert_called_with(50)


# ===========================================================================
# Audit preservation
# ===========================================================================

class TestAuditPreservation:
    def test_approve_does_not_overwrite_audit_snapshot(self):
        snapshot = json.dumps({"dimension": "engagement", "risk_level": "high"})
        review = _stub_review(audit_snapshot_json=snapshot)
        db = _make_db(review=review)
        SVC.approve_review(db, review_id=77, reviewed_by="jane@example.com")
        # audit_snapshot_json must be unchanged
        assert review.audit_snapshot_json == snapshot

    def test_reject_does_not_overwrite_audit_snapshot(self):
        snapshot = json.dumps({"confidence": 0.88})
        review = _stub_review(audit_snapshot_json=snapshot)
        db = _make_db(review=review)
        SVC.reject_review(db, review_id=77, reviewed_by="bob@example.com",
                          review_notes="Disputed.")
        assert review.audit_snapshot_json == snapshot

    def test_defer_does_not_overwrite_audit_snapshot(self):
        snapshot = json.dumps({"entity_id": "101"})
        review = _stub_review(audit_snapshot_json=snapshot)
        db = _make_db(review=review)
        SVC.defer_review(db, review_id=77, reviewed_by="carol@example.com",
                         governance_reason="Needs more context.")
        assert review.audit_snapshot_json == snapshot


# ===========================================================================
# Orchestration integration: governance review auto-created on generate_new
# ===========================================================================

class TestOrchestrationGovernanceIntegration:
    """Verify that the orchestration service calls create_pending_review
    when a new AIInterpretation is generated."""

    def _make_orchestration_stubs(self):
        """Return extraction/evaluation mocks that trigger the generate_new branch."""
        from tests.unit.test_sentinel_orchestration_service import (
            _make_extraction, _evaluation_generate, _ai_result,
        )
        mock_extractor = MagicMock()
        mock_extractor.extract_student_state.return_value = _make_extraction()

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate_material_change.return_value = _evaluation_generate(invalidate=False)

        mock_governance = MagicMock()

        return mock_extractor, mock_evaluator, mock_governance, _ai_result()

    def test_governance_create_called_on_generate(self):
        from services.sentinel_orchestration_service import SentinelOrchestrationService

        extractor, evaluator, mock_gov, ai = self._make_orchestration_stubs()

        svc = SentinelOrchestrationService(
            extraction_service=extractor,
            evaluation_service=evaluator,
            governance_service=mock_gov,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 99)

        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            svc.orchestrate_student_evaluation(db, "101", "student")

        mock_gov.create_pending_review.assert_called_once()

    def test_governance_create_receives_correct_entity_id(self):
        from services.sentinel_orchestration_service import SentinelOrchestrationService

        extractor, evaluator, mock_gov, ai = self._make_orchestration_stubs()

        svc = SentinelOrchestrationService(
            extraction_service=extractor,
            evaluation_service=evaluator,
            governance_service=mock_gov,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 99)

        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            svc.orchestrate_student_evaluation(db, "101", "student")

        call_kwargs = mock_gov.create_pending_review.call_args[1]
        assert call_kwargs["entity_id"]   == "101"
        assert call_kwargs["entity_type"] == "student"

    def test_governance_not_called_on_reuse(self):
        from services.sentinel_orchestration_service import SentinelOrchestrationService
        from tests.unit.test_sentinel_orchestration_service import (
            _make_extraction, _evaluation_reuse, _make_interpretation,
        )

        mock_extractor = MagicMock()
        mock_extractor.extract_student_state.return_value = _make_extraction()

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate_material_change.return_value = _evaluation_reuse()

        mock_gov = MagicMock()

        svc = SentinelOrchestrationService(
            extraction_service=mock_extractor,
            evaluation_service=mock_evaluator,
            governance_service=mock_gov,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            _make_interpretation()
        )

        svc.orchestrate_student_evaluation(db, "101", "student")
        mock_gov.create_pending_review.assert_not_called()

    def test_orchestration_succeeds_even_if_governance_create_raises(self):
        """Governance failure must not abort the orchestration call."""
        from services.sentinel_orchestration_service import SentinelOrchestrationService
        from tests.unit.test_sentinel_orchestration_service import (
            _make_extraction, _evaluation_generate, _ai_result,
        )

        mock_extractor = MagicMock()
        mock_extractor.extract_student_state.return_value = _make_extraction()

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate_material_change.return_value = _evaluation_generate(invalidate=False)

        mock_gov = MagicMock()
        mock_gov.create_pending_review.side_effect = RuntimeError("DB connection lost")

        svc = SentinelOrchestrationService(
            extraction_service=mock_extractor,
            evaluation_service=mock_evaluator,
            governance_service=mock_gov,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 99)

        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            result = svc.orchestrate_student_evaluation(db, "101", "student")

        # Orchestration still succeeds with a full result
        assert result["generated_new_interpretation"] is True
        assert "interpretation_id" in result


# ===========================================================================
# Pydantic schemas
# ===========================================================================

class TestGovernanceReviewSchemas:
    def test_create_schema_accepts_valid_data(self):
        from api.schemas.governance_review import GovernanceReviewCreate
        schema = GovernanceReviewCreate(
            interpretation_id=42,
            entity_id="101",
            entity_type="student",
            risk_level="high",
            confidence=0.88,
            governance_reason="Risk escalation detected.",
        )
        assert schema.interpretation_id == 42
        assert schema.confidence        == pytest.approx(0.88)

    def test_create_schema_rejects_confidence_above_1(self):
        from api.schemas.governance_review import GovernanceReviewCreate
        with pytest.raises(ValidationError):
            GovernanceReviewCreate(
                interpretation_id=1, entity_id="x", entity_type="student",
                risk_level="low", confidence=1.01, governance_reason="test",
            )

    def test_create_schema_rejects_empty_governance_reason(self):
        from api.schemas.governance_review import GovernanceReviewCreate
        with pytest.raises(ValidationError):
            GovernanceReviewCreate(
                interpretation_id=1, entity_id="x", entity_type="student",
                risk_level="low", confidence=0.5, governance_reason="",
            )

    def test_read_schema_from_orm_stub(self):
        from api.schemas.governance_review import GovernanceReviewRead
        now = datetime.utcnow()
        review = SimpleNamespace(
            id=1, created_at=now, updated_at=now,
            interpretation_id=42, entity_id="101", entity_type="student",
            status="pending", reviewed_by=None, reviewed_at=None,
            review_notes=None, governance_reason="Risk detected.",
            risk_level="high", confidence=0.88, audit_snapshot_json=None,
            is_active=True,
        )
        schema = GovernanceReviewRead.model_validate(review)
        assert schema.id             == 1
        assert schema.status         == GovernanceReviewStatus.pending
        assert schema.confidence     == pytest.approx(0.88)
        assert schema.is_active      is True

    def test_approve_schema_requires_reviewed_by(self):
        from api.schemas.governance_review import GovernanceReviewApprove
        with pytest.raises(ValidationError):
            GovernanceReviewApprove(reviewed_by="")

    def test_reject_schema_requires_both_fields(self):
        from api.schemas.governance_review import GovernanceReviewReject
        with pytest.raises(ValidationError):
            GovernanceReviewReject(reviewed_by="bob@example.com", review_notes="")

    def test_defer_schema_requires_governance_reason(self):
        from api.schemas.governance_review import GovernanceReviewDefer
        with pytest.raises(ValidationError):
            GovernanceReviewDefer(reviewed_by="carol@example.com", governance_reason="")

    def test_audit_snapshot_json_field_validator_parses_string(self):
        from api.schemas.governance_review import GovernanceReviewCreate
        snap = {"dimension": "engagement", "risk_level": "high"}
        schema = GovernanceReviewCreate(
            interpretation_id=1, entity_id="x", entity_type="student",
            risk_level="high", confidence=0.9, governance_reason="test",
            audit_snapshot_json=json.dumps(snap),
        )
        assert isinstance(schema.audit_snapshot_json, dict)
        assert schema.audit_snapshot_json["dimension"] == "engagement"

    def test_read_schema_audit_snapshot_json_parses_from_string(self):
        from api.schemas.governance_review import GovernanceReviewRead
        now = datetime.utcnow()
        snap = json.dumps({"risk_level": "critical"})
        review = SimpleNamespace(
            id=2, created_at=now, updated_at=now,
            interpretation_id=5, entity_id="101", entity_type="student",
            status="pending", reviewed_by=None, reviewed_at=None,
            review_notes=None, governance_reason="test",
            risk_level="critical", confidence=0.91,
            audit_snapshot_json=snap, is_active=True,
        )
        schema = GovernanceReviewRead.model_validate(review)
        assert isinstance(schema.audit_snapshot_json, dict)
        assert schema.audit_snapshot_json["risk_level"] == "critical"
