"""Unit tests for SentinelOrchestrationService.

All tests are isolated — no database session, no network, no real AI call.
The SQLAlchemy session and all service dependencies are replaced with MagicMock
or SimpleNamespace stubs controlled per-test.

Test categories:
  - Output shape: required keys always present
  - No-prior interpretation flow: generates new, no invalidation
  - Reuse flow: cached interpretation returned, AI bypassed entirely
  - Regeneration flow: material change detected, new interpretation generated
  - Invalidation flow: active prior invalidated when generate_new fires
  - Fallback flow: AI returns fallback (confidence=0.0, risk_level="unknown")
  - Invalid dimension: returns error payload, no pipeline execution
  - Governance payload structure and content fidelity
  - AI generation bypass verification during reuse
  - DB write verification: db.add / db.commit / db.refresh called on generation
  - Invalidation write verification: is_active=False, invalidated_at set
  - _signals_to_kpis conversion helper
  - _compute_source_hash determinism
  - _build_governance_from_interpretation round-trip
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from services.sentinel_orchestration_service import (
    SentinelOrchestrationService,
    _FALLBACK_GOVERNANCE,
    _GOVERNANCE_PAYLOAD_KEYS,
    _RESULT_KEYS,
)

# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

_ENTITY_ID   = "101"
_ENTITY_TYPE = "student"
_DIMENSION   = "engagement"


def _make_db() -> MagicMock:
    """Return a mock session that supports .query().filter().order_by().first()."""
    db = MagicMock()
    q  = MagicMock()
    q.filter.return_value       = q
    q.order_by.return_value     = q
    q.first.return_value        = None
    db.query.return_value       = q
    return db


def _make_extraction(risk_level: str = "medium", has_data: bool = True) -> dict:
    """Minimal extract_student_state() return value."""
    signals = [
        {"name": "last_activity_days", "value": 5,    "unit": "days",  "confidence": 0.90},
        {"name": "past_10_days_logon", "value": 3,    "unit": "count", "confidence": 0.85},
    ]
    fingerprints = [
        {"pattern_name": "passive_disengagement", "score": 0.72, "risk_level": risk_level},
    ]
    return {
        "entity_id":   _ENTITY_ID,
        "entity_type": _ENTITY_TYPE,
        "dimensions": {
            "engagement": {
                "signals":             signals if has_data else [],
                "fingerprints":        fingerprints if has_data else [],
                "risk_level":          risk_level,
                "confidence":          0.87,
                "data_available":      has_data,
                "source_record_count": 1,
                "notes":               "test",
            },
            "retention_risk":               {"signals": [], "fingerprints": [], "data_available": False, "risk_level": "unknown", "confidence": 0.0, "source_record_count": 0, "notes": ""},
            "communication_responsiveness": {"signals": [], "fingerprints": [], "data_available": False, "risk_level": "unknown", "confidence": 0.0, "source_record_count": 0, "notes": ""},
            "intervention_effectiveness":   {"signals": [], "fingerprints": [], "data_available": False, "risk_level": "unknown", "confidence": 0.0, "source_record_count": 0, "notes": ""},
        },
        "source_tables":  ["AI_ChatBot_TriggerData"],
        "extracted_at":   datetime.utcnow().isoformat(),
        "signal_summary": {
            "total_signals":          2,
            "dimensions_with_data":   1,
            "overall_confidence":     0.87,
            "highest_risk_dimension": "engagement",
            "highest_risk_level":     risk_level,
        },
    }


def _make_interpretation(
    id_val: int = 10,
    risk_level: str = "low",
    confidence: float = 0.80,
    is_active: bool = True,
    explainability: list = None,
) -> SimpleNamespace:
    """Minimal AIInterpretation-like stub."""
    expl = explainability if explainability is not None else ["signal A is normal."]
    return SimpleNamespace(
        id                   = id_val,
        entity_id            = _ENTITY_ID,
        entity_type          = _ENTITY_TYPE,
        dimension            = _DIMENSION,
        confidence           = confidence,
        risk_level           = risk_level,
        summary              = "Student is on track.",
        recommended_action   = "No action needed.",
        explainability_json  = json.dumps(expl),
        source_metrics_hash  = "a" * 64,
        source_snapshot_json = "{}",
        is_active            = is_active,
        invalidated_at       = None,
        invalidation_reason  = None,
        stale_after          = datetime(2099, 1, 1),
        created_at           = datetime(2025, 1, 1),
        generated_by         = "claude",
    )


def _evaluation_reuse() -> dict:
    return {
        "reuse_existing":           True,
        "generate_new":             False,
        "invalidate_existing":      False,
        "reason":                   "No material change detected.",
        "severity":                 "none",
        "confidence_delta":         0.01,
        "risk_changed":             False,
        "new_fingerprint_detected": False,
    }


def _evaluation_generate(invalidate: bool = False) -> dict:
    return {
        "reuse_existing":           False,
        "generate_new":             True,
        "invalidate_existing":      invalidate,
        "reason":                   "Risk escalation detected.",
        "severity":                 "high",
        "confidence_delta":         None,
        "risk_changed":             True,
        "new_fingerprint_detected": False,
    }


def _ai_result(risk_level: str = "high", confidence: float = 0.88) -> dict:
    return {
        "summary":            "Student shows strong disengagement.",
        "risk_level":         risk_level,
        "confidence":         confidence,
        "recommended_action": "Schedule a 1:1 check-in within 48 hours.",
        "explainability":     ["Login frequency is low.", "Attendance dropped."],
    }


def _ai_fallback() -> dict:
    return {
        "summary":            "AI insight unavailable. Review KPI data manually.",
        "risk_level":         "unknown",
        "confidence":         0.0,
        "recommended_action": "Manual review required — AI service did not return a result.",
        "explainability":     ["AI service unavailable — this is a safe fallback response."],
    }


def _build_service(extraction=None, evaluation=None) -> SentinelOrchestrationService:
    """Return an orchestration service with mocked sub-services."""
    mock_extractor = MagicMock()
    mock_extractor.extract_student_state.return_value = (
        extraction if extraction is not None else _make_extraction()
    )
    mock_evaluator = MagicMock()
    mock_evaluator.evaluate_material_change.return_value = (
        evaluation if evaluation is not None else _evaluation_reuse()
    )
    return SentinelOrchestrationService(
        extraction_service=mock_extractor,
        evaluation_service=mock_evaluator,
    )


# ===========================================================================
# Output shape contract
# ===========================================================================

class TestOutputShape:
    def test_all_result_keys_present_on_reuse_flow(self):
        svc = _build_service(evaluation=_evaluation_reuse())
        db  = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            _make_interpretation()
        )
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert _RESULT_KEYS == set(result.keys())

    def test_governance_payload_has_all_required_keys(self):
        svc = _build_service(evaluation=_evaluation_reuse())
        db  = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            _make_interpretation()
        )
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert _GOVERNANCE_PAYLOAD_KEYS == set(result["governance_payload"].keys())

    def test_shadow_mode_is_always_true(self):
        svc = _build_service(evaluation=_evaluation_reuse())
        db  = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            _make_interpretation()
        )
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["shadow_mode"] is True

    def test_orchestrated_at_is_iso8601(self):
        svc = _build_service(evaluation=_evaluation_reuse())
        db  = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            _make_interpretation()
        )
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        datetime.fromisoformat(result["orchestrated_at"])

    def test_entity_id_and_type_echoed(self):
        svc = _build_service(evaluation=_evaluation_reuse())
        db  = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            _make_interpretation()
        )
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["entity_id"]   == _ENTITY_ID
        assert result["entity_type"] == _ENTITY_TYPE

    def test_dimension_echoed(self):
        svc = _build_service(evaluation=_evaluation_reuse())
        db  = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            _make_interpretation()
        )
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE, dimension="engagement")
        assert result["dimension"] == "engagement"


# ===========================================================================
# Invalid dimension
# ===========================================================================

class TestInvalidDimension:
    def test_unknown_dimension_returns_result_without_pipeline_execution(self):
        svc = _build_service()
        db  = _make_db()
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE, dimension="mood")
        assert result["generated_new_interpretation"] is False
        assert result["used_cached_interpretation"]   is False

    def test_unknown_dimension_extraction_not_called(self):
        svc = _build_service()
        db  = _make_db()
        svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE, dimension="mood")
        svc._extractor.extract_student_state.assert_not_called()

    def test_unknown_dimension_result_has_all_keys(self):
        svc = _build_service()
        db  = _make_db()
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE, dimension="mood")
        assert _RESULT_KEYS == set(result.keys())

    def test_unknown_dimension_interpretation_id_is_none(self):
        svc = _build_service()
        db  = _make_db()
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE, dimension="bad")
        assert result["interpretation_id"] is None


# ===========================================================================
# No-prior interpretation flow
# ===========================================================================

class TestNoPriorInterpretationFlow:
    def _setup(self, ai_result=None):
        """Orchestrator with no cached interpretation, evaluation triggers generate."""
        svc = _build_service(evaluation=_evaluation_generate(invalidate=False))
        db  = _make_db()
        # No prior interpretation in DB
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 99)
        return svc, db

    def test_generated_new_interpretation_is_true(self):
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            svc, db = self._setup()
            result  = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["generated_new_interpretation"] is True

    def test_used_cached_is_false(self):
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            svc, db = self._setup()
            result  = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["used_cached_interpretation"] is False

    def test_db_add_and_commit_called(self):
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            svc, db = self._setup()
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        # interpretation add + governance review add = 2 calls
        assert db.add.call_count == 2
        db.commit.assert_called()

    def test_no_invalidation_when_no_prior(self):
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            svc, db = self._setup()
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        # commit #1 = new interpretation, commit #2 = governance review (no invalidation commit)
        assert db.commit.call_count == 2

    def test_governance_payload_reflects_ai_result(self):
        ai = _ai_result(risk_level="high", confidence=0.88)
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            svc, db = self._setup()
            result  = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        gp = result["governance_payload"]
        assert gp["risk_level"]   == "high"
        assert gp["confidence"]   == pytest.approx(0.88)
        assert gp["explainability"] == ai["explainability"]


# ===========================================================================
# Reuse flow
# ===========================================================================

class TestReuseFlow:
    def _setup(self, interp=None):
        interp = interp or _make_interpretation(id_val=42)
        svc    = _build_service(evaluation=_evaluation_reuse())
        db     = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = interp
        return svc, db, interp

    def test_used_cached_interpretation_is_true(self):
        svc, db, interp = self._setup()
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["used_cached_interpretation"] is True

    def test_generated_new_is_false(self):
        svc, db, interp = self._setup()
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["generated_new_interpretation"] is False

    def test_interpretation_id_matches_cached(self):
        svc, db, interp = self._setup(_make_interpretation(id_val=42))
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["interpretation_id"] == 42

    def test_ai_not_called_on_reuse(self):
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight"
        ) as mock_ai:
            svc, db, _ = self._setup()
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
            mock_ai.assert_not_called()

    def test_db_not_written_on_reuse(self):
        svc, db, _ = self._setup()
        svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_governance_payload_built_from_cached_interpretation(self):
        interp = _make_interpretation(
            risk_level="medium", confidence=0.75,
            explainability=["reason A", "reason B"],
        )
        svc, db, _ = self._setup(interp)
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        gp = result["governance_payload"]
        assert gp["risk_level"] == "medium"
        assert gp["confidence"] == pytest.approx(0.75)
        assert gp["explainability"] == ["reason A", "reason B"]

    def test_evaluation_result_included_in_output(self):
        svc, db, _ = self._setup()
        result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["evaluation_result"]["reuse_existing"] is True
        assert result["evaluation_result"]["generate_new"]   is False


# ===========================================================================
# Regeneration flow
# ===========================================================================

class TestRegenerationFlow:
    def _setup(self, interp=None, ai=None, invalidate=False):
        interp = interp or _make_interpretation(id_val=7, is_active=True)
        ai     = ai     or _ai_result()
        svc    = _build_service(evaluation=_evaluation_generate(invalidate=invalidate))
        db     = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = interp
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 200)
        return svc, db, interp, ai

    def test_generated_new_interpretation_true(self):
        svc, db, interp, ai = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["generated_new_interpretation"] is True

    def test_used_cached_is_false(self):
        svc, db, interp, ai = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["used_cached_interpretation"] is False

    def test_db_add_called_with_ai_interpretation(self):
        from services.models import AIInterpretation
        svc, db, interp, ai = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        # first add = AIInterpretation; second add = GovernanceReview
        added_obj = db.add.call_args_list[0][0][0]
        assert isinstance(added_obj, AIInterpretation)

    def test_persisted_interpretation_has_correct_risk_level(self):
        ai = _ai_result(risk_level="critical", confidence=0.95)
        svc, db, interp, _ = self._setup(ai=ai)
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        added_obj = db.add.call_args[0][0]
        assert added_obj.risk_level   == "critical"
        assert added_obj.confidence   == pytest.approx(0.95)

    def test_persisted_interpretation_entity_id_matches(self):
        svc, db, interp, ai = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        added_obj = db.add.call_args_list[0][0][0]
        assert added_obj.entity_id   == _ENTITY_ID
        assert added_obj.entity_type == _ENTITY_TYPE
        assert added_obj.dimension   == _DIMENSION

    def test_persisted_interpretation_has_source_hash(self):
        svc, db, interp, ai = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        added_obj = db.add.call_args_list[0][0][0]
        assert added_obj.source_metrics_hash is not None
        assert len(added_obj.source_metrics_hash) == 64

    def test_persisted_interpretation_has_explainability_json(self):
        svc, db, interp, ai = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        added_obj = db.add.call_args_list[0][0][0]
        parsed = json.loads(added_obj.explainability_json)
        assert isinstance(parsed, list)
        assert len(parsed) > 0

    def test_governance_payload_reflects_new_ai_result(self):
        ai = _ai_result(risk_level="high", confidence=0.92)
        svc, db, interp, _ = self._setup(ai=ai)
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=ai,
        ):
            result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        gp = result["governance_payload"]
        assert gp["risk_level"] == "high"
        assert gp["confidence"] == pytest.approx(0.92)


# ===========================================================================
# Invalidation flow
# ===========================================================================

class TestInvalidationFlow:
    def test_prior_interpretation_marked_inactive(self):
        interp = _make_interpretation(id_val=5, is_active=True)
        svc    = _build_service(evaluation=_evaluation_generate(invalidate=True))
        db     = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = interp
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 300)

        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)

        assert interp.is_active is False

    def test_prior_interpretation_invalidated_at_set(self):
        interp = _make_interpretation(id_val=5, is_active=True)
        svc    = _build_service(evaluation=_evaluation_generate(invalidate=True))
        db     = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = interp
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 300)

        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)

        assert interp.invalidated_at is not None
        assert isinstance(interp.invalidated_at, datetime)

    def test_prior_interpretation_invalidation_reason_set(self):
        interp = _make_interpretation(id_val=5, is_active=True)
        svc    = _build_service(evaluation=_evaluation_generate(invalidate=True))
        db     = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = interp
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 300)

        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)

        assert interp.invalidation_reason is not None
        assert len(interp.invalidation_reason) > 0

    def test_commit_called_twice_when_invalidation_plus_new(self):
        interp = _make_interpretation(id_val=5, is_active=True)
        svc    = _build_service(evaluation=_evaluation_generate(invalidate=True))
        db     = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = interp
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 300)

        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)

        # commit #1 = invalidation, commit #2 = new interpretation, commit #3 = governance review
        assert db.commit.call_count == 3

    def test_no_invalidation_when_flag_false(self):
        interp = _make_interpretation(id_val=5, is_active=True)
        svc    = _build_service(evaluation=_evaluation_generate(invalidate=False))
        db     = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = interp
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 300)

        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)

        assert interp.is_active is True           # unchanged
        # commit #1 = new interpretation, commit #2 = governance review (no invalidation commit)
        assert db.commit.call_count == 2


# ===========================================================================
# Fallback AI result
# ===========================================================================

class TestFallbackAIResult:
    def _setup(self):
        svc = _build_service(evaluation=_evaluation_generate(invalidate=False))
        db  = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 99)
        return svc, db

    def test_fallback_still_persists_interpretation(self):
        svc, db = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_fallback(),
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        # interpretation add + governance review add = 2 calls
        assert db.add.call_count == 2

    def test_fallback_generated_by_is_fallback_enum(self):
        from services.models import InterpretationGeneratedBy
        svc, db = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_fallback(),
        ):
            svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        # first add = AIInterpretation; second add = GovernanceReview
        added_obj = db.add.call_args_list[0][0][0]
        assert added_obj.generated_by == InterpretationGeneratedBy.fallback

    def test_fallback_governance_payload_risk_unknown(self):
        svc, db = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_fallback(),
        ):
            result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["governance_payload"]["risk_level"] == "unknown"
        assert result["governance_payload"]["confidence"] == pytest.approx(0.0)

    def test_fallback_generated_new_is_true(self):
        svc, db = self._setup()
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_fallback(),
        ):
            result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["generated_new_interpretation"] is True


# ===========================================================================
# Evaluation result pass-through
# ===========================================================================

class TestEvaluationResultPassThrough:
    def test_evaluation_result_included_on_generate_path(self):
        eval_dict = _evaluation_generate(invalidate=True)
        svc = _build_service(evaluation=eval_dict)
        db  = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 99)
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["evaluation_result"]["generate_new"] is True
        assert result["evaluation_result"]["severity"] == "high"

    def test_evaluation_reason_preserved(self):
        eval_dict = _evaluation_generate()
        svc = _build_service(evaluation=eval_dict)
        db  = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        db.refresh.side_effect = lambda obj: setattr(obj, "id", 99)
        with patch(
            "services.sentinel_orchestration_service.generate_ai_insight",
            return_value=_ai_result(),
        ):
            result = svc.orchestrate_student_evaluation(db, _ENTITY_ID, _ENTITY_TYPE)
        assert "Risk escalation" in result["evaluation_result"]["reason"]


# ===========================================================================
# _signals_to_kpis helper
# ===========================================================================

class TestSignalsToKpis:
    def test_converts_valid_signals(self):
        signals = [
            {"name": "last_activity_days", "value": 5,  "confidence": 0.90, "unit": "days"},
            {"name": "attendance_pct",     "value": 80, "confidence": 0.85, "unit": "percent"},
        ]
        kpis = SentinelOrchestrationService._signals_to_kpis(signals)
        assert len(kpis) == 2
        assert kpis[0]["kpi_name"] == "last_activity_days"
        assert kpis[0]["confidence"] == pytest.approx(0.90)

    def test_excludes_null_value_signals(self):
        signals = [
            {"name": "valid",   "value": 5,    "confidence": 0.90, "unit": "days"},
            {"name": "missing", "value": None, "confidence": 0.0,  "unit": "days"},
        ]
        kpis = SentinelOrchestrationService._signals_to_kpis(signals)
        assert len(kpis) == 1
        assert kpis[0]["kpi_name"] == "valid"

    def test_excludes_zero_confidence_signals(self):
        signals = [
            {"name": "low_conf", "value": 3, "confidence": 0.0, "unit": "days"},
        ]
        kpis = SentinelOrchestrationService._signals_to_kpis(signals)
        assert kpis == []

    def test_empty_signals_returns_empty_list(self):
        assert SentinelOrchestrationService._signals_to_kpis([]) == []

    def test_output_contains_sentinel_source_pattern(self):
        signals = [{"name": "x", "value": 1, "confidence": 0.8, "unit": "count"}]
        kpis = SentinelOrchestrationService._signals_to_kpis(signals)
        assert kpis[0]["source_pattern"] == "sentinel_extraction"


# ===========================================================================
# _compute_source_hash determinism
# ===========================================================================

class TestComputeSourceHash:
    def test_same_inputs_produce_same_hash(self):
        signals = [{"name": "a", "value": 5}, {"name": "b", "value": 10}]
        fps     = [{"pattern_name": "fp1"}]
        h1 = SentinelOrchestrationService._compute_source_hash(signals, fps)
        h2 = SentinelOrchestrationService._compute_source_hash(signals, fps)
        assert h1 == h2

    def test_different_values_produce_different_hash(self):
        signals_a = [{"name": "a", "value": 5}]
        signals_b = [{"name": "a", "value": 6}]
        fps       = []
        h1 = SentinelOrchestrationService._compute_source_hash(signals_a, fps)
        h2 = SentinelOrchestrationService._compute_source_hash(signals_b, fps)
        assert h1 != h2

    def test_hash_is_64_hex_chars(self):
        h = SentinelOrchestrationService._compute_source_hash([], [])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_null_signals_excluded_from_hash(self):
        signals_with_null    = [{"name": "a", "value": None}, {"name": "b", "value": 5}]
        signals_without_null = [{"name": "b", "value": 5}]
        fps = []
        h1 = SentinelOrchestrationService._compute_source_hash(signals_with_null,    fps)
        h2 = SentinelOrchestrationService._compute_source_hash(signals_without_null, fps)
        assert h1 == h2


# ===========================================================================
# _build_governance_from_interpretation
# ===========================================================================

class TestBuildGovernanceFromInterpretation:
    def test_all_fields_extracted(self):
        interp = _make_interpretation(
            risk_level="high", confidence=0.91,
            explainability=["signal A is elevated."]
        )
        gp = SentinelOrchestrationService._build_governance_from_interpretation(interp)
        assert gp["risk_level"]   == "high"
        assert gp["confidence"]   == pytest.approx(0.91)
        assert gp["explainability"] == ["signal A is elevated."]

    def test_malformed_explainability_json_returns_empty_list(self):
        interp = _make_interpretation()
        interp.explainability_json = "not-valid-json{{{"
        gp = SentinelOrchestrationService._build_governance_from_interpretation(interp)
        assert gp["explainability"] == []

    def test_none_explainability_json_returns_empty_list(self):
        interp = _make_interpretation()
        interp.explainability_json = None
        gp = SentinelOrchestrationService._build_governance_from_interpretation(interp)
        assert gp["explainability"] == []

    def test_none_recommended_action_returns_empty_string(self):
        interp = _make_interpretation()
        interp.recommended_action = None
        gp = SentinelOrchestrationService._build_governance_from_interpretation(interp)
        assert gp["recommended_action"] == ""
