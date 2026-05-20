"""Sentinel Shadow-Mode Orchestration Service.

Connects the four layers of the Sentinel intelligence pipeline into a single,
governed, auditable evaluation flow:

  Layer 1 — SentinelExtractionService     (read-only DB extraction + normalization)
  Layer 2 — AIInterpretation query        (load latest active cached result)
  Layer 3 — MaterialChangeEvaluationService (deterministic reuse/regenerate gate)
  Layer 4 — AI generation + persistence   (Claude call + AIInterpretation write)

Shadow-mode contract
────────────────────
This service is shadow-mode only. It:
  - Reads from all Sentinel tables
  - Writes ONLY to AI_ChatBot_AIInterpretations
  - Issues NO outbound messages
  - Calls NO trigger workers
  - Modifies NO student-facing data

The only observable side effects are:
  1. A new AIInterpretation row when material change is detected
  2. An existing AIInterpretation row invalidated (is_active=False)

Determinism guarantee
─────────────────────
Steps 1–3 are fully deterministic. Step 4 (AI generation) is probabilistic but
is gated behind the deterministic material-change evaluation, which ensures it
only runs when student state has verifiably changed. The governance payload is
always present in the output regardless of which branch executed.

Audit trace
───────────
Every orchestration call emits a structured log at each step boundary. The
output dict contains the full evaluation_result from the material-change service
so callers can replay the decision reasoning without re-running the pipeline.

Public API
──────────
  SentinelOrchestrationService.orchestrate_student_evaluation(
      db, entity_id, entity_type, dimension="engagement"
  ) → dict  (see _RESULT_KEYS for guaranteed output shape)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from config.database import SENTINEL_LIVE
from services.ai_insight_service import generate_ai_insight
from services.governance_review_service import GovernanceReviewService
from services.material_change_evaluation_service import MaterialChangeEvaluationService
from services.models import AIInterpretation, InterpretationGeneratedBy
from services.sentinel_extraction_service import SentinelExtractionService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_VALID_DIMENSIONS = frozenset({
    "engagement",
    "retention_risk",
    "communication_responsiveness",
    "intervention_effectiveness",
})

# Keys that must always be present in the output dict
_RESULT_KEYS = frozenset({
    "entity_id",
    "entity_type",
    "dimension",
    "evaluation_result",
    "used_cached_interpretation",
    "generated_new_interpretation",
    "interpretation_id",
    "governance_payload",
    "shadow_mode",
    "orchestrated_at",
})

_GOVERNANCE_PAYLOAD_KEYS = frozenset({
    "risk_level",
    "confidence",
    "recommended_action",
    "explainability",
    "summary",
})

# Fallback governance payload — returned when AI is unavailable or not called
_FALLBACK_GOVERNANCE: dict[str, Any] = {
    "risk_level":         "unknown",
    "confidence":         0.0,
    "summary":            "AI evaluation unavailable. Manual review required.",
    "recommended_action": "Review student signals manually.",
    "explainability":     ["AI service unavailable — this is a safe fallback response."],
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SentinelOrchestrationService:
    """Governed shadow-mode orchestration pipeline for student AI evaluations.

    Wires extraction → cache lookup → material-change gate → AI generation →
    persistence into a single deterministic, auditable flow.

    Instances are stateless. db is passed per-call to allow caller-controlled
    transaction scoping.
    """

    def __init__(
        self,
        extraction_service:  Optional[SentinelExtractionService]       = None,
        evaluation_service:  Optional[MaterialChangeEvaluationService]  = None,
        governance_service:  Optional[GovernanceReviewService]          = None,
    ) -> None:
        self._extractor  = extraction_service  or SentinelExtractionService(use_mock=not SENTINEL_LIVE)
        self._evaluator  = evaluation_service  or MaterialChangeEvaluationService()
        self._governance = governance_service  or GovernanceReviewService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def orchestrate_student_evaluation(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
        dimension: str = "engagement",
    ) -> dict[str, Any]:
        """Run the full Sentinel evaluation pipeline for one entity/dimension.

        Parameters
        ----------
        db            SQLAlchemy session.  Writes only to AIInterpretation.
        entity_id     String representation of the student identifier.
        entity_type   Semantic entity label — currently only "student" is supported.
        dimension     One of the V1 Sentinel dimensions.  Defaults to "engagement".

        Returns
        -------
        dict  — guaranteed to contain all keys in _RESULT_KEYS.
                Never raises; returns a fallback payload on any internal error.
        """
        orchestrated_at = datetime.utcnow().isoformat()

        logger.info(
            "SentinelOrchestration: starting for entity_id=%r entity_type=%r dimension=%r",
            entity_id, entity_type, dimension,
        )

        # Validate dimension early — return error payload rather than raise
        if dimension not in _VALID_DIMENSIONS:
            logger.warning(
                "SentinelOrchestration: unknown dimension=%r for entity_id=%r",
                dimension, entity_id,
            )
            return self._error_payload(
                entity_id, entity_type, dimension, orchestrated_at,
                reason=f"Unknown dimension {dimension!r}. "
                       f"Valid values: {sorted(_VALID_DIMENSIONS)}",
            )

        try:
            return self._run_pipeline(
                db, entity_id, entity_type, dimension, orchestrated_at
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "SentinelOrchestration: unhandled error for entity_id=%r dimension=%r: %s",
                entity_id, dimension, exc,
            )
            return self._error_payload(
                entity_id, entity_type, dimension, orchestrated_at,
                reason=f"Internal orchestration error: {exc}",
            )

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
        dimension: str,
        orchestrated_at: str,
    ) -> dict[str, Any]:

        # ── STEP 1: Extract current student state ─────────────────────
        logger.info(
            "SentinelOrchestration[%s]: STEP 1 — extracting student state", entity_id
        )
        extraction = self._extractor.extract_student_state(db, entity_id, entity_type)
        dim_data   = extraction["dimensions"].get(dimension, {})

        current_kpis         = self._signals_to_kpis(dim_data.get("signals", []))
        current_fingerprints = dim_data.get("fingerprints", [])

        logger.info(
            "SentinelOrchestration[%s]: extracted kpis=%d fingerprints=%d",
            entity_id, len(current_kpis), len(current_fingerprints),
        )

        # ── STEP 2: Load latest active interpretation ──────────────────
        logger.info(
            "SentinelOrchestration[%s]: STEP 2 — loading latest active interpretation "
            "for dimension=%r", entity_id, dimension,
        )
        latest_interpretation = self._load_latest_interpretation(
            db, entity_id, entity_type, dimension
        )
        logger.info(
            "SentinelOrchestration[%s]: latest_interpretation=%s",
            entity_id,
            f"id={getattr(latest_interpretation, 'id', None)}" if latest_interpretation else "None",
        )

        # ── STEP 3: Material change evaluation ────────────────────────
        logger.info(
            "SentinelOrchestration[%s]: STEP 3 — running material change evaluation",
            entity_id,
        )
        evaluation = self._evaluator.evaluate_material_change(
            entity_id=entity_id,
            entity_type=entity_type,
            dimension=dimension,
            current_kpis=current_kpis,
            current_fingerprints=current_fingerprints,
            latest_interpretation=latest_interpretation,
        )
        logger.info(
            "SentinelOrchestration[%s]: evaluation decision — "
            "reuse=%s generate_new=%s severity=%r reason=%r",
            entity_id,
            evaluation["reuse_existing"],
            evaluation["generate_new"],
            evaluation["severity"],
            evaluation["reason"][:100],
        )

        # ── STEP 4: Decision branch ────────────────────────────────────

        if evaluation["reuse_existing"]:
            return self._reuse_branch(
                entity_id, entity_type, dimension, orchestrated_at,
                evaluation, latest_interpretation,
            )

        # generate_new is True
        return self._generate_branch(
            db, entity_id, entity_type, dimension, orchestrated_at,
            evaluation, latest_interpretation,
            current_kpis, current_fingerprints, dim_data,
        )

    def _reuse_branch(
        self,
        entity_id: str,
        entity_type: str,
        dimension: str,
        orchestrated_at: str,
        evaluation: dict[str, Any],
        latest_interpretation: Any,
    ) -> dict[str, Any]:
        """STEP 4a: reuse_existing=True — return cached interpretation, skip AI."""
        logger.info(
            "SentinelOrchestration[%s]: STEP 4 — REUSE — "
            "returning cached interpretation id=%s",
            entity_id,
            getattr(latest_interpretation, "id", None),
        )

        governance_payload = self._build_governance_from_interpretation(latest_interpretation)
        return {
            "entity_id":                  entity_id,
            "entity_type":                entity_type,
            "dimension":                  dimension,
            "evaluation_result":          evaluation,
            "used_cached_interpretation": True,
            "generated_new_interpretation": False,
            "interpretation_id":          getattr(latest_interpretation, "id", None),
            "governance_payload":         governance_payload,
            "shadow_mode":                True,
            "orchestrated_at":            orchestrated_at,
        }

    def _generate_branch(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
        dimension: str,
        orchestrated_at: str,
        evaluation: dict[str, Any],
        latest_interpretation: Any,
        current_kpis: list[dict],
        current_fingerprints: list[dict],
        dim_data: dict[str, Any],
    ) -> dict[str, Any]:
        """STEP 4b: generate_new=True — call AI, optionally invalidate, persist."""
        logger.info(
            "SentinelOrchestration[%s]: STEP 4 — GENERATE — "
            "calling AI generation service", entity_id,
        )

        # ── Optionally invalidate the existing active interpretation ──
        if evaluation.get("invalidate_existing") and latest_interpretation is not None:
            self._invalidate_interpretation(db, latest_interpretation, evaluation["reason"])

        # ── Call AI generation ─────────────────────────────────────────
        ai_result = generate_ai_insight({
            "entity_id":   entity_id,
            "entity_type": entity_type,
            "kpis":        current_kpis,
            "fingerprints": current_fingerprints,
        })

        generated_by = (
            InterpretationGeneratedBy.fallback
            if ai_result.get("risk_level") == "unknown"
            else InterpretationGeneratedBy.claude
        )

        logger.info(
            "SentinelOrchestration[%s]: AI result — risk_level=%r confidence=%.3f generated_by=%s",
            entity_id,
            ai_result.get("risk_level"),
            ai_result.get("confidence", 0.0),
            generated_by,
        )

        # ── Build source hash + snapshot ──────────────────────────────
        source_hash     = self._compute_source_hash(
            dim_data.get("signals", []), current_fingerprints
        )
        source_snapshot = {
            "signals":      dim_data.get("signals", []),
            "fingerprints": current_fingerprints,
            "dimension":    dimension,
        }

        # ── Persist new interpretation ─────────────────────────────────
        new_interp = AIInterpretation(
            entity_id              = entity_id,
            entity_type            = entity_type,
            dimension              = dimension,
            confidence             = float(ai_result.get("confidence", 0.0)),
            risk_level             = ai_result.get("risk_level", "unknown"),
            summary                = ai_result.get("summary", ""),
            recommended_action     = ai_result.get("recommended_action"),
            explainability_json    = json.dumps(ai_result.get("explainability", [])),
            source_metrics_hash    = source_hash,
            source_snapshot_json   = json.dumps(source_snapshot),
            generated_by           = generated_by,
            model_name             = "claude-sonnet-4-6" if generated_by == InterpretationGeneratedBy.claude else None,
        )

        db.add(new_interp)
        db.commit()
        db.refresh(new_interp)

        logger.info(
            "SentinelOrchestration[%s]: persisted new interpretation id=%s "
            "risk_level=%r confidence=%.3f",
            entity_id,
            getattr(new_interp, "id", None),
            new_interp.risk_level,
            new_interp.confidence,
        )

        # ── Auto-create GovernanceReview(status=pending) ──────────────
        audit_snapshot = {
            "interpretation_id": getattr(new_interp, "id", None),
            "dimension":         dimension,
            "risk_level":        new_interp.risk_level,
            "confidence":        new_interp.confidence,
            "generated_by":      str(generated_by),
            "evaluation_reason": evaluation.get("reason", ""),
            "orchestrated_at":   orchestrated_at,
        }
        try:
            self._governance.create_pending_review(
                db                = db,
                interpretation_id = getattr(new_interp, "id", 0),
                entity_id         = entity_id,
                entity_type       = entity_type,
                risk_level        = new_interp.risk_level,
                confidence        = new_interp.confidence,
                governance_reason = (
                    f"New {dimension} interpretation generated "
                    f"(severity={evaluation.get('severity', 'unknown')}): "
                    f"{evaluation.get('reason', '')}"[:500]
                ),
                audit_snapshot    = audit_snapshot,
            )
            logger.info(
                "SentinelOrchestration[%s]: governance review created for interpretation id=%s",
                entity_id, getattr(new_interp, "id", None),
            )
        except Exception as gov_exc:  # noqa: BLE001
            # Governance review creation must never fail the orchestration call.
            # Log the error and continue — the interpretation is already persisted.
            logger.error(
                "SentinelOrchestration[%s]: failed to create governance review "
                "for interpretation id=%s: %s",
                entity_id, getattr(new_interp, "id", None), gov_exc,
            )

        governance_payload = {
            "risk_level":         ai_result.get("risk_level", "unknown"),
            "confidence":         float(ai_result.get("confidence", 0.0)),
            "summary":            ai_result.get("summary", ""),
            "recommended_action": ai_result.get("recommended_action", ""),
            "explainability":     ai_result.get("explainability", []),
        }

        return {
            "entity_id":                    entity_id,
            "entity_type":                  entity_type,
            "dimension":                    dimension,
            "evaluation_result":            evaluation,
            "used_cached_interpretation":   False,
            "generated_new_interpretation": True,
            "interpretation_id":            getattr(new_interp, "id", None),
            "governance_payload":           governance_payload,
            "shadow_mode":                  True,
            "orchestrated_at":              orchestrated_at,
        }

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _load_latest_interpretation(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
        dimension: str,
    ) -> Optional[AIInterpretation]:
        """Return the most recently created active interpretation for this entity/dimension."""
        return (
            db.query(AIInterpretation)
            .filter(
                AIInterpretation.entity_id   == entity_id,
                AIInterpretation.entity_type == entity_type,
                AIInterpretation.dimension   == dimension,
                AIInterpretation.is_active   == True,  # noqa: E712
            )
            .order_by(AIInterpretation.created_at.desc())
            .first()
        )

    def _invalidate_interpretation(
        self,
        db: Session,
        interpretation: Any,
        reason: str,
    ) -> None:
        """Mark an existing interpretation inactive. Does not delete."""
        interpretation.is_active          = False
        interpretation.invalidated_at     = datetime.utcnow()
        interpretation.invalidation_reason = reason[:500]  # guard against overlong reasons
        db.add(interpretation)
        db.commit()
        logger.info(
            "SentinelOrchestration: invalidated interpretation id=%s reason=%r",
            getattr(interpretation, "id", None),
            reason[:80],
        )

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _signals_to_kpis(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert normalized extraction signals into the KPI format expected by
        MaterialChangeEvaluationService and generate_ai_insight().

        Only includes signals that have a non-None value and a positive confidence.
        """
        return [
            {
                "kpi_name":       sig["name"],
                "confidence":     float(sig.get("confidence", 0.0)),
                "source_pattern": "sentinel_extraction",
                "sample_size":    1,
                "value":          sig.get("value"),
                "unit":           sig.get("unit"),
            }
            for sig in signals
            if sig.get("value") is not None and float(sig.get("confidence", 0.0)) > 0.0
        ]

    @staticmethod
    def _compute_source_hash(
        signals: list[dict[str, Any]],
        fingerprints: list[dict[str, Any]],
    ) -> str:
        """Deterministic SHA-256 of non-null signal values + fingerprint names.

        Stable across calls: dict keys are sorted before serialization.
        Used to detect identical inputs and skip redundant AI calls.
        """
        payload = {
            "signals": sorted(
                [
                    {"name": s.get("name"), "value": str(s.get("value"))}
                    for s in signals
                    if s.get("value") is not None
                ],
                key=lambda x: x["name"],
            ),
            "fingerprints": sorted(
                fp.get("pattern_name", "") for fp in fingerprints
            ),
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _build_governance_from_interpretation(
        interpretation: Any,
    ) -> dict[str, Any]:
        """Build a governance payload from an existing AIInterpretation object."""
        explainability: list[str] = []
        raw = getattr(interpretation, "explainability_json", None)
        if raw:
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, list):
                    explainability = parsed
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "risk_level":         str(getattr(interpretation, "risk_level",         "unknown")),
            "confidence":         float(getattr(interpretation, "confidence",        0.0)),
            "summary":            str(getattr(interpretation, "summary",             "")),
            "recommended_action": str(getattr(interpretation, "recommended_action",  "") or ""),
            "explainability":     explainability,
        }

    # ------------------------------------------------------------------
    # Error / fallback payload builder
    # ------------------------------------------------------------------

    @staticmethod
    def _error_payload(
        entity_id: str,
        entity_type: str,
        dimension: str,
        orchestrated_at: str,
        reason: str,
    ) -> dict[str, Any]:
        governance = _FALLBACK_GOVERNANCE.copy()
        governance["summary"] = reason
        return {
            "entity_id":                    entity_id,
            "entity_type":                  entity_type,
            "dimension":                    dimension,
            "evaluation_result":            {
                "reuse_existing":           False,
                "generate_new":             False,
                "invalidate_existing":      False,
                "reason":                   reason,
                "severity":                 "none",
                "confidence_delta":         None,
                "risk_changed":             False,
                "new_fingerprint_detected": False,
            },
            "used_cached_interpretation":   False,
            "generated_new_interpretation": False,
            "interpretation_id":            None,
            "governance_payload":           governance,
            "shadow_mode":                  True,
            "orchestrated_at":              orchestrated_at,
        }
