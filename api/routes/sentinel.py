"""Sentinel Dashboard — read-only observability endpoints.

All routes are GET-only. No mutations, no outbound actions.
Returns mock data when MSSQL is not configured so the dashboard
works out of the box in local/dev without a database connection.

Endpoints
─────────
GET /sentinel/governance/reviews              — all reviews, optional ?status= filter
GET /sentinel/governance/reviews/pending      — pending reviews shorthand
GET /sentinel/interpretations/{entity_id}/latest   — most-recent active interpretation
GET /sentinel/interpretations/{entity_id}/history  — full interpretation history
GET /sentinel/analytics/reuse-metrics         — aggregate pipeline statistics
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Generator, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from config.database import MSSQL_CONFIGURED, SessionLocal
from services.models import AIInterpretation, GovernanceReview, GovernanceReviewStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sentinel", tags=["sentinel"])


# ---------------------------------------------------------------------------
# Optional DB dependency — yields None when MSSQL is not configured
# ---------------------------------------------------------------------------

def _get_db_optional() -> Generator:
    if not MSSQL_CONFIGURED or SessionLocal is None:
        yield None
        return
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Mock data (used when MSSQL is not configured)
# ---------------------------------------------------------------------------

_NOW = "2026-05-18T10:00:00"
_NOW_MINUS_1H = "2026-05-18T09:00:00"
_NOW_MINUS_3H = "2026-05-18T07:00:00"
_NOW_MINUS_1D = "2026-05-17T10:00:00"
_NOW_MINUS_2D = "2026-05-16T10:00:00"
_NOW_MINUS_5D = "2026-05-13T10:00:00"
_STALE_IN_14D = "2026-06-01T10:00:00"

_MOCK_REVIEWS: list[dict[str, Any]] = [
    {
        "id": 1, "created_at": _NOW_MINUS_3H, "updated_at": _NOW_MINUS_3H,
        "interpretation_id": 101, "entity_id": "student_101", "entity_type": "student",
        "status": "pending", "reviewed_by": None, "reviewed_at": None,
        "review_notes": None,
        "governance_reason": "New engagement interpretation generated (severity=high): LastActivityDays ≥ 7 indicates elevated risk",
        "risk_level": "high", "confidence": 0.87, "is_active": True,
    },
    {
        "id": 2, "created_at": _NOW_MINUS_3H, "updated_at": _NOW_MINUS_3H,
        "interpretation_id": 102, "entity_id": "student_202", "entity_type": "student",
        "status": "pending", "reviewed_by": None, "reviewed_at": None,
        "review_notes": None,
        "governance_reason": "New engagement interpretation generated (severity=critical): LastActivityDays ≥ 14 and HWsBehind ≥ 3",
        "risk_level": "critical", "confidence": 0.92, "is_active": True,
    },
    {
        "id": 3, "created_at": _NOW_MINUS_1D, "updated_at": _NOW_MINUS_1D,
        "interpretation_id": 98, "entity_id": "student_303", "entity_type": "student",
        "status": "pending", "reviewed_by": None, "reviewed_at": None,
        "review_notes": None,
        "governance_reason": "New retention_risk interpretation generated (severity=medium): attendance below threshold",
        "risk_level": "medium", "confidence": 0.71, "is_active": True,
    },
    {
        "id": 4, "created_at": _NOW_MINUS_2D, "updated_at": _NOW_MINUS_1H,
        "interpretation_id": 90, "entity_id": "student_404", "entity_type": "student",
        "status": "approved", "reviewed_by": "admin@colaberry.com",
        "reviewed_at": _NOW_MINUS_1H, "review_notes": "Risk level confirmed — mentor outreach appropriate",
        "governance_reason": "New engagement interpretation generated (severity=high)",
        "risk_level": "high", "confidence": 0.83, "is_active": True,
    },
    {
        "id": 5, "created_at": _NOW_MINUS_2D, "updated_at": _NOW_MINUS_1D,
        "interpretation_id": 85, "entity_id": "student_505", "entity_type": "student",
        "status": "approved", "reviewed_by": "admin@colaberry.com",
        "reviewed_at": _NOW_MINUS_1D, "review_notes": "Verified against manual engagement check",
        "governance_reason": "New engagement interpretation generated (severity=medium)",
        "risk_level": "medium", "confidence": 0.75, "is_active": True,
    },
    {
        "id": 6, "created_at": _NOW_MINUS_5D, "updated_at": _NOW_MINUS_2D,
        "interpretation_id": 70, "entity_id": "student_101", "entity_type": "student",
        "status": "rejected", "reviewed_by": "supervisor@colaberry.com",
        "reviewed_at": _NOW_MINUS_2D,
        "review_notes": "Confidence too low — student was on approved leave, data is stale",
        "governance_reason": "New engagement interpretation generated (severity=critical)",
        "risk_level": "critical", "confidence": 0.55, "is_active": True,
    },
    {
        "id": 7, "created_at": _NOW_MINUS_5D, "updated_at": _NOW_MINUS_5D,
        "interpretation_id": 65, "entity_id": "student_606", "entity_type": "student",
        "status": "deferred", "reviewed_by": "admin@colaberry.com",
        "reviewed_at": _NOW_MINUS_5D, "review_notes": None,
        "governance_reason": "Awaiting updated attendance data before confirming risk level",
        "risk_level": "high", "confidence": 0.68, "is_active": True,
    },
]

_MOCK_INTERPRETATIONS: dict[str, list[dict[str, Any]]] = {
    "student_101": [
        {
            "id": 101, "created_at": _NOW_MINUS_3H, "updated_at": _NOW_MINUS_3H,
            "invalidated_at": None, "entity_id": "student_101", "entity_type": "student",
            "dimension": "engagement", "interpretation_version": 3,
            "confidence": 0.87, "risk_level": "high",
            "summary": (
                "Student 101 has not logged in for 9 days and has 2 assignments overdue. "
                "Engagement pattern indicates elevated dropout risk."
            ),
            "recommended_action": "Schedule mentor check-in within 48 hours",
            "explainability": [
                "LastActivityDays=9 exceeds high-risk threshold of 7",
                "HWsBehind=2 indicates assignment backlog",
                "AttendancePercentage=72% is below the 80% benchmark",
                "Past10DaysLogon=1 indicates near-zero recent engagement",
            ],
            "generated_by": "claude",
            "model_name": "claude-sonnet-4-6",
            "source_metrics_hash": "a3f8c1d2e4b7901234567890abcdef1234567890abcdef1234567890abcdef12",  # pragma: allowlist secret
            "stale_after": _STALE_IN_14D, "is_active": True, "invalidation_reason": None,
        },
        {
            "id": 95, "created_at": _NOW_MINUS_2D, "updated_at": _NOW_MINUS_3H,
            "invalidated_at": _NOW_MINUS_3H, "entity_id": "student_101", "entity_type": "student",
            "dimension": "engagement", "interpretation_version": 2,
            "confidence": 0.79, "risk_level": "medium",
            "summary": "Student 101 engagement has declined but remains above critical threshold.",
            "recommended_action": "Monitor for another 3 days before intervention",
            "explainability": [
                "LastActivityDays=6 is below high-risk threshold",
                "HWsBehind=1 minor backlog",
            ],
            "generated_by": "claude",
            "model_name": "claude-sonnet-4-6",
            "source_metrics_hash": "b4a9d3e5f8c0123456789012345678901234567890abcdef1234567890abcdef",  # pragma: allowlist secret
            "stale_after": _NOW_MINUS_1H, "is_active": False,
            "invalidation_reason": "Material change: risk escalated from medium → high; confidence delta 0.87-0.79=0.08",
        },
        {
            "id": 82, "created_at": _NOW_MINUS_5D, "updated_at": _NOW_MINUS_2D,
            "invalidated_at": _NOW_MINUS_2D, "entity_id": "student_101", "entity_type": "student",
            "dimension": "engagement", "interpretation_version": 1,
            "confidence": 0.63, "risk_level": "low",
            "summary": "Student 101 engagement is within expected range for this stage.",
            "recommended_action": None,
            "explainability": [
                "LastActivityDays=2 indicates recent activity",
                "AttendancePercentage=89% above benchmark",
            ],
            "generated_by": "claude",
            "model_name": "claude-sonnet-4-6",
            "source_metrics_hash": "c5b0e4f6a9d1234567890123456789012345678901234567890abcdef123456",  # pragma: allowlist secret
            "stale_after": _NOW_MINUS_1D, "is_active": False,
            "invalidation_reason": "Material change: new fingerprint detected; stale_after exceeded",
        },
    ],
    "student_202": [
        {
            "id": 102, "created_at": _NOW_MINUS_3H, "updated_at": _NOW_MINUS_3H,
            "invalidated_at": None, "entity_id": "student_202", "entity_type": "student",
            "dimension": "engagement", "interpretation_version": 1,
            "confidence": 0.92, "risk_level": "critical",
            "summary": (
                "Student 202 shows critical disengagement: 14+ days inactive, "
                "3 assignments overdue, attendance at 58%."
            ),
            "recommended_action": "Immediate escalation to program director required",
            "explainability": [
                "LastActivityDays=15 exceeds critical threshold of 14",
                "HWsBehind=3 severe assignment backlog",
                "AttendancePercentage=58% critically below benchmark",
                "DaysInStatus=45 indicates prolonged stagnation",
            ],
            "generated_by": "claude",
            "model_name": "claude-sonnet-4-6",
            "source_metrics_hash": "d6c1f5a7b0e2345678901234567890123456789012345678901234567890abcd",  # pragma: allowlist secret
            "stale_after": _STALE_IN_14D, "is_active": True, "invalidation_reason": None,
        },
    ],
}

_MOCK_REUSE_METRICS: dict[str, Any] = {
    "total_interpretations": 24,
    "active_interpretations": 8,
    "invalidated_interpretations": 16,
    "by_risk_level": {"low": 6, "medium": 8, "high": 7, "critical": 3, "unknown": 0},
    "by_generated_by": {"claude": 20, "fallback": 2, "deterministic_engine": 2},
    "material_change_triggers": {
        "confidence_delta": 8,
        "risk_escalation": 6,
        "new_fingerprint": 4,
        "stale": 3,
        "cross_dimension": 2,
        "reuse_default": 1,
    },
    "governance_summary": {
        "pending": 3,
        "approved": 18,
        "rejected": 1,
        "deferred": 2,
        "total": 24,
    },
    "note": "Reuse events are not persisted — count reflects interpretations that bypassed regeneration based on source_metrics_hash cache hits.",
}


# ---------------------------------------------------------------------------
# Route helpers
# ---------------------------------------------------------------------------

def _serialize_review(r: GovernanceReview) -> dict[str, Any]:
    return {
        "id":                 r.id,
        "created_at":         r.created_at.isoformat() if r.created_at else None,
        "updated_at":         r.updated_at.isoformat() if r.updated_at else None,
        "interpretation_id":  r.interpretation_id,
        "entity_id":          r.entity_id,
        "entity_type":        r.entity_type,
        "status":             r.status if isinstance(r.status, str) else r.status.value,
        "reviewed_by":        r.reviewed_by,
        "reviewed_at":        r.reviewed_at.isoformat() if r.reviewed_at else None,
        "review_notes":       r.review_notes,
        "governance_reason":  r.governance_reason,
        "risk_level":         r.risk_level,
        "confidence":         r.confidence,
        "is_active":          r.is_active,
    }


def _serialize_interpretation(i: AIInterpretation) -> dict[str, Any]:
    explainability: list[str] = []
    if i.explainability_json:
        try:
            explainability = json.loads(i.explainability_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id":                     i.id,
        "created_at":             i.created_at.isoformat() if i.created_at else None,
        "updated_at":             i.updated_at.isoformat() if i.updated_at else None,
        "invalidated_at":         i.invalidated_at.isoformat() if i.invalidated_at else None,
        "entity_id":              i.entity_id,
        "entity_type":            i.entity_type,
        "dimension":              i.dimension,
        "interpretation_version": i.interpretation_version,
        "confidence":             i.confidence,
        "risk_level":             i.risk_level,
        "summary":                i.summary,
        "recommended_action":     i.recommended_action,
        "explainability":         explainability,
        "generated_by":           i.generated_by,
        "model_name":             i.model_name,
        "source_metrics_hash":    i.source_metrics_hash,
        "stale_after":            i.stale_after.isoformat() if i.stale_after else None,
        "is_active":              i.is_active,
        "invalidation_reason":    i.invalidation_reason,
    }


# ---------------------------------------------------------------------------
# Governance endpoints
# ---------------------------------------------------------------------------

@router.get("/governance/reviews")
def get_governance_reviews(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected, deferred"),
    limit:  int           = Query(100, le=500),
    db:     Optional[Session] = Depends(_get_db_optional),
) -> dict[str, Any]:
    if db is None:
        filtered = _MOCK_REVIEWS
        if status:
            filtered = [r for r in filtered if r["status"] == status]
        return {"reviews": filtered[:limit], "total": len(filtered[:limit]), "source": "mock"}

    q = db.query(GovernanceReview)
    if status:
        q = q.filter(GovernanceReview.status == status)
    rows = q.order_by(GovernanceReview.created_at.desc()).limit(limit).all()
    return {"reviews": [_serialize_review(r) for r in rows], "total": len(rows), "source": "db"}


@router.get("/governance/reviews/pending")
def get_pending_reviews(
    limit: int = Query(100, le=500),
    db:    Optional[Session] = Depends(_get_db_optional),
) -> dict[str, Any]:
    if db is None:
        pending = [r for r in _MOCK_REVIEWS if r["status"] == "pending"]
        return {"reviews": pending[:limit], "total": len(pending[:limit]), "source": "mock"}

    rows = (
        db.query(GovernanceReview)
        .filter(GovernanceReview.status == GovernanceReviewStatus.pending)
        .order_by(GovernanceReview.created_at.asc())
        .limit(limit)
        .all()
    )
    return {"reviews": [_serialize_review(r) for r in rows], "total": len(rows), "source": "db"}


# ---------------------------------------------------------------------------
# Interpretation endpoints
# NOTE: /history/{entity_id} must be declared BEFORE /{entity_id}/latest
#       to avoid route shadowing — FastAPI matches in declaration order.
# ---------------------------------------------------------------------------

@router.get("/interpretations/{entity_id}/latest")
def get_latest_interpretation(
    entity_id: str,
    dimension: Optional[str] = Query(None),
    db:        Optional[Session] = Depends(_get_db_optional),
) -> dict[str, Any]:
    if db is None:
        history = _MOCK_INTERPRETATIONS.get(entity_id, [])
        active = [i for i in history if i["is_active"]]
        if dimension:
            active = [i for i in active if i["dimension"] == dimension]
        return {
            "entity_id": entity_id,
            "latest": active[0] if active else None,
            "source": "mock",
        }

    q = (
        db.query(AIInterpretation)
        .filter(
            AIInterpretation.entity_id == entity_id,
            AIInterpretation.is_active == True,  # noqa: E712
        )
    )
    if dimension:
        q = q.filter(AIInterpretation.dimension == dimension)
    row = q.order_by(AIInterpretation.created_at.desc()).first()
    return {
        "entity_id": entity_id,
        "latest": _serialize_interpretation(row) if row else None,
        "source": "db",
    }


@router.get("/interpretations/{entity_id}/history")
def get_interpretation_history(
    entity_id: str,
    limit:     int           = Query(20, le=100),
    dimension: Optional[str] = Query(None),
    db:        Optional[Session] = Depends(_get_db_optional),
) -> dict[str, Any]:
    if db is None:
        history = _MOCK_INTERPRETATIONS.get(entity_id, [])
        if dimension:
            history = [i for i in history if i["dimension"] == dimension]
        return {
            "entity_id": entity_id,
            "history": history[:limit],
            "total": len(history[:limit]),
            "source": "mock",
        }

    q = (
        db.query(AIInterpretation)
        .filter(AIInterpretation.entity_id == entity_id)
    )
    if dimension:
        q = q.filter(AIInterpretation.dimension == dimension)
    rows = q.order_by(AIInterpretation.created_at.desc()).limit(limit).all()
    return {
        "entity_id": entity_id,
        "history": [_serialize_interpretation(r) for r in rows],
        "total": len(rows),
        "source": "db",
    }


# ---------------------------------------------------------------------------
# Analytics endpoint
# ---------------------------------------------------------------------------

@router.get("/analytics/reuse-metrics")
def get_reuse_metrics(
    db: Optional[Session] = Depends(_get_db_optional),
) -> dict[str, Any]:
    if db is None:
        return {**_MOCK_REUSE_METRICS, "source": "mock"}

    total   = db.query(AIInterpretation).count()
    active  = db.query(AIInterpretation).filter(AIInterpretation.is_active == True).count()   # noqa: E712
    invalid = db.query(AIInterpretation).filter(AIInterpretation.is_active == False).count()  # noqa: E712

    by_risk: dict[str, int] = {}
    for level in ("low", "medium", "high", "critical", "unknown"):
        by_risk[level] = (
            db.query(AIInterpretation)
            .filter(AIInterpretation.risk_level == level)
            .count()
        )

    by_gen: dict[str, int] = {}
    for gen in ("claude", "fallback", "deterministic_engine"):
        by_gen[gen] = (
            db.query(AIInterpretation)
            .filter(AIInterpretation.generated_by == gen)
            .count()
        )

    gov: dict[str, int] = {}
    for s in ("pending", "approved", "rejected", "deferred"):
        gov[s] = db.query(GovernanceReview).filter(GovernanceReview.status == s).count()
    gov["total"] = sum(gov.values())

    return {
        "total_interpretations":    total,
        "active_interpretations":   active,
        "invalidated_interpretations": invalid,
        "by_risk_level":            by_risk,
        "by_generated_by":          by_gen,
        "governance_summary":       gov,
        "note": (
            "Reuse events are not persisted — count reflects interpretations "
            "that bypassed regeneration based on source_metrics_hash cache hits."
        ),
        "source": "db",
    }
