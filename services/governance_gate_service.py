"""GovernanceGateService — approval gate for the Sentinel delivery pipeline.

Implements FR-EXEC-001: Approval-Gated Execution.
Directive: directives/governance_gate_contract.md

check_delivery_approved() is deterministic and read-only.
It never calls an LLM, never commits, and never raises.
"""

import logging

from services.models import AIInterpretation, GovernanceReview

logger = logging.getLogger(__name__)

_BLOCKED_STATUSES = {"pending", "rejected", "deferred"}

_STATUS_TO_REASON = {
    "approved": "approved_review",
    "pending":  "pending",
    "rejected": "rejected",
    "deferred": "deferred",
}


class GovernanceGateService:

    def check_delivery_approved(
        self,
        db,
        entity_id: str,
        entity_type: str = "student",
    ) -> dict:
        try:
            interp = (
                db.query(AIInterpretation)
                .filter(
                    AIInterpretation.entity_id == entity_id,
                    AIInterpretation.entity_type == entity_type,
                    AIInterpretation.is_active == True,
                )
                .order_by(AIInterpretation.created_at.desc())
                .first()
            )

            if interp is None:
                return {"approved": True, "reason": "no_sentinel_data", "review_id": None}

            review = (
                db.query(GovernanceReview)
                .filter(GovernanceReview.interpretation_id == interp.id)
                .order_by(GovernanceReview.created_at.desc())
                .first()
            )

            if review is None:
                logger.error(
                    "GovernanceGate: no GovernanceReview row for entity_id=%r "
                    "interpretation_id=%r — pipeline fault; delivery blocked.",
                    entity_id, interp.id,
                )
                return {"approved": False, "reason": "no_governance_review", "review_id": None}

            status = str(review.status)
            reason = _STATUS_TO_REASON.get(status, "no_governance_review")
            approved = status == "approved"
            return {"approved": approved, "reason": reason, "review_id": review.id}

        except Exception as exc:
            logger.error(
                "GovernanceGate: gate check failed for entity_id=%r — "
                "fail-open: delivery proceeding. Error: %s",
                entity_id, exc,
            )
            return {"approved": True, "reason": "gate_error", "review_id": None}
