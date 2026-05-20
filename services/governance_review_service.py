"""Governance Review Service.

Manages the human-governed review queue for AI-generated interpretations.

Every new AIInterpretation is automatically enqueued with status="pending".
No downstream automation may execute until a reviewer has approved the record.

Design constraints
──────────────────
- Historical reviews are never deleted. All decisions are preserved in place.
- Status transitions are updates to the existing review row, not new rows.
- The audit_snapshot_json captured at creation is immutable: it is never overwritten.
- review_notes is required for reject; governance_reason is required for defer.
- No outbound actions, no messaging, no mentor assignment.

Status lifecycle
────────────────
  pending → approved  : reviewer confirms the interpretation is actionable
  pending → rejected  : reviewer disputes the interpretation (review_notes required)
  pending → deferred  : reviewer requests more context (governance_reason required)
  any     → deferred  : edge-case re-deferral after initial decision

Public API
──────────
  GovernanceReviewService.create_pending_review(...)   → GovernanceReview
  GovernanceReviewService.approve_review(...)          → GovernanceReview
  GovernanceReviewService.reject_review(...)           → GovernanceReview
  GovernanceReviewService.defer_review(...)            → GovernanceReview
  GovernanceReviewService.get_pending_reviews(...)     → list[GovernanceReview]
  GovernanceReviewService.get_review_history(...)      → list[GovernanceReview]
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from services.models import GovernanceReview, GovernanceReviewStatus

logger = logging.getLogger(__name__)


class GovernanceReviewService:
    """Manages creation and lifecycle transitions of GovernanceReview records.

    All methods accept a db session as their first parameter and commit within
    the method body.  The session is never stored on the instance.
    """

    # ------------------------------------------------------------------
    # Public API — creation
    # ------------------------------------------------------------------

    def create_pending_review(
        self,
        db: Session,
        interpretation_id: int,
        entity_id: str,
        entity_type: str,
        risk_level: str,
        confidence: float,
        governance_reason: str,
        audit_snapshot: Optional[dict[str, Any]] = None,
    ) -> GovernanceReview:
        """Create a new GovernanceReview with status=pending.

        Called automatically by the orchestration layer immediately after a new
        AIInterpretation is persisted. Callers must not set status manually.

        Parameters
        ----------
        interpretation_id   PK of the AIInterpretation this review covers.
        entity_id           Student identifier (denormalized for fast query).
        entity_type         Entity class label.
        risk_level          Risk level copied from the interpretation.
        confidence          Confidence score copied from the interpretation.
        governance_reason   Why this interpretation was queued for review.
        audit_snapshot      Optional dict capturing any additional context at
                            creation time. Serialized to JSON and immutable.
        """
        audit_json = json.dumps(audit_snapshot) if audit_snapshot is not None else None

        review = GovernanceReview(
            interpretation_id   = interpretation_id,
            entity_id           = entity_id,
            entity_type         = entity_type,
            status              = GovernanceReviewStatus.pending,
            governance_reason   = governance_reason,
            risk_level          = risk_level,
            confidence          = float(confidence),
            audit_snapshot_json = audit_json,
        )

        db.add(review)
        db.commit()
        db.refresh(review)

        logger.info(
            "GovernanceReview: created pending review id=%s "
            "interpretation_id=%s entity_id=%r risk_level=%r",
            review.id, interpretation_id, entity_id, risk_level,
        )
        return review

    # ------------------------------------------------------------------
    # Public API — decisions
    # ------------------------------------------------------------------

    def approve_review(
        self,
        db: Session,
        review_id: int,
        reviewed_by: str,
        review_notes: Optional[str] = None,
    ) -> GovernanceReview:
        """Mark a review approved.

        Parameters
        ----------
        review_id    PK of the GovernanceReview to approve.
        reviewed_by  Identity of the reviewer (name, email, or system id).
        review_notes Optional free-text annotation.

        Raises
        ------
        ValueError  if review_id is not found.
        """
        review = self._load_or_raise(db, review_id)

        review.status      = GovernanceReviewStatus.approved
        review.reviewed_by = reviewed_by
        review.reviewed_at = datetime.utcnow()
        if review_notes is not None:
            review.review_notes = review_notes

        db.add(review)
        db.commit()
        db.refresh(review)

        logger.info(
            "GovernanceReview: approved review id=%s by=%r",
            review_id, reviewed_by,
        )
        return review

    def reject_review(
        self,
        db: Session,
        review_id: int,
        reviewed_by: str,
        review_notes: str,
    ) -> GovernanceReview:
        """Mark a review rejected.

        review_notes is required for rejection — a rejection without a stated
        reason is not an auditable governance decision.

        Parameters
        ----------
        review_id    PK of the GovernanceReview to reject.
        reviewed_by  Identity of the reviewer.
        review_notes Required explanation of the rejection reason.

        Raises
        ------
        ValueError  if review_id is not found.
        ValueError  if review_notes is empty or whitespace-only.
        """
        if not review_notes or not review_notes.strip():
            raise ValueError(
                "review_notes is required for rejection. "
                "A rejection without a stated reason is not an auditable governance decision."
            )

        review = self._load_or_raise(db, review_id)

        review.status       = GovernanceReviewStatus.rejected
        review.reviewed_by  = reviewed_by
        review.reviewed_at  = datetime.utcnow()
        review.review_notes = review_notes

        db.add(review)
        db.commit()
        db.refresh(review)

        logger.info(
            "GovernanceReview: rejected review id=%s by=%r notes=%r",
            review_id, reviewed_by, review_notes[:80],
        )
        return review

    def defer_review(
        self,
        db: Session,
        review_id: int,
        reviewed_by: str,
        governance_reason: str,
    ) -> GovernanceReview:
        """Mark a review deferred, requesting more context before a decision.

        governance_reason is required for deferral — it must explain what
        additional information is needed.

        Parameters
        ----------
        review_id          PK of the GovernanceReview to defer.
        reviewed_by        Identity of the reviewer.
        governance_reason  Required explanation of why review was deferred.

        Raises
        ------
        ValueError  if review_id is not found.
        ValueError  if governance_reason is empty or whitespace-only.
        """
        if not governance_reason or not governance_reason.strip():
            raise ValueError(
                "governance_reason is required for deferral. "
                "A deferral without a stated reason is not an auditable governance decision."
            )

        review = self._load_or_raise(db, review_id)

        review.status            = GovernanceReviewStatus.deferred
        review.reviewed_by       = reviewed_by
        review.reviewed_at       = datetime.utcnow()
        review.governance_reason = governance_reason

        db.add(review)
        db.commit()
        db.refresh(review)

        logger.info(
            "GovernanceReview: deferred review id=%s by=%r reason=%r",
            review_id, reviewed_by, governance_reason[:80],
        )
        return review

    # ------------------------------------------------------------------
    # Public API — queries
    # ------------------------------------------------------------------

    def get_pending_reviews(
        self,
        db: Session,
        entity_type: Optional[str] = None,
        risk_level: Optional[str] = None,
        limit: int = 100,
    ) -> list[GovernanceReview]:
        """Return active pending reviews, optionally filtered.

        Parameters
        ----------
        entity_type  If provided, restrict results to this entity class.
        risk_level   If provided, restrict results to this risk level.
        limit        Maximum rows to return (default 100, hard cap at 500).
        """
        limit = min(limit, 500)

        q = (
            db.query(GovernanceReview)
            .filter(
                GovernanceReview.status    == GovernanceReviewStatus.pending,
                GovernanceReview.is_active == True,  # noqa: E712
            )
        )
        if entity_type is not None:
            q = q.filter(GovernanceReview.entity_type == entity_type)
        if risk_level is not None:
            q = q.filter(GovernanceReview.risk_level == risk_level)

        return (
            q.order_by(GovernanceReview.created_at.asc())
             .limit(limit)
             .all()
        )

    def get_review_history(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
        limit: int = 50,
    ) -> list[GovernanceReview]:
        """Return all review records for a given entity, newest first.

        Includes all statuses (pending, approved, rejected, deferred) to
        provide a complete audit chain.
        """
        limit = min(limit, 200)

        return (
            db.query(GovernanceReview)
            .filter(
                GovernanceReview.entity_id   == entity_id,
                GovernanceReview.entity_type == entity_type,
            )
            .order_by(GovernanceReview.created_at.desc())
            .limit(limit)
            .all()
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_or_raise(self, db: Session, review_id: int) -> GovernanceReview:
        """Load a GovernanceReview by PK or raise ValueError."""
        review: Optional[GovernanceReview] = (
            db.query(GovernanceReview)
            .filter(GovernanceReview.id == review_id)
            .first()
        )
        if review is None:
            raise ValueError(
                f"GovernanceReview id={review_id} not found. "
                "Cannot apply a governance decision to a non-existent review."
            )
        return review
