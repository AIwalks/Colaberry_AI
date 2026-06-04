"""Recommendation Learning Service.

Computes success rates for recommendation keys by joining
AI_ChatBot_Recommendations to AI_ChatBot_InterventionOutcomes on cbm_id.

Learning key
────────────
recommendation_key is the primary grouping identifier.  recommendation_type
is retained in the output for display purposes only and is never used as a
learning signal.

Eligibility
───────────
Only outcomes where eligible_for_learning=True are counted.  Inconclusive
outcomes (eligible_for_learning=False) are excluded from both numerator and
denominator — they carry no signal about recommendation effectiveness.

success_rate
────────────
  None           when total_eligible = 0  (no labeled outcomes yet)
  0.0 – 1.0      total_improved / total_eligible otherwise

has_sufficient_sample
─────────────────────
  True   when total_eligible >= min_sample  (default 10)
  False  otherwise — rate exists but is statistically unreliable

Defensive contract
──────────────────
All public methods are read-only and non-fatal.  Any exception is caught,
logged, and the method returns [] / original candidate order.  Callers are
never affected by learning query failures.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from services.models import InterventionOutcome, Recommendation

logger = logging.getLogger(__name__)


class RecommendationLearningService:
    """Computes recommendation success rates and candidate rankings.

    All methods accept a db Session as their first parameter.
    The session is never stored on the instance.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_success_rates(
        self,
        db: Session,
        *,
        dimension:  Optional[str] = None,
        risk_level: Optional[str] = None,
        min_sample: int = 10,
    ) -> list[dict]:
        """Return success rate per recommendation_key.

        Joins AI_ChatBot_Recommendations to AI_ChatBot_InterventionOutcomes
        on cbm_id.  Groups by recommendation_key.  Excludes outcomes where
        eligible_for_learning is not True.

        Optional filters:
          dimension  — restrict to recommendations with this dimension value.
          risk_level — restrict to recommendations with this risk_level value.
          min_sample — minimum eligible outcomes required for
                       has_sufficient_sample=True (default 10).

        Returns a list of dicts, one per recommendation_key:
          recommendation_key    — the granular learning identifier
          recommendation_type   — broad action category (display only)
          total_eligible        — count of improved + not_improved outcomes
          total_improved        — count of improved outcomes
          success_rate          — float 0.0–1.0, or None when total_eligible=0
          has_sufficient_sample — True when total_eligible >= min_sample

        Returns [] on any exception.
        """
        try:
            conditions = [
                InterventionOutcome.eligible_for_learning == True,
                Recommendation.is_active == True,
            ]
            if dimension is not None:
                conditions.append(Recommendation.dimension == dimension)
            if risk_level is not None:
                conditions.append(Recommendation.risk_level == risk_level)

            rows = (
                db.query(
                    Recommendation.recommendation_key,
                    Recommendation.recommendation_type,
                    func.count(InterventionOutcome.id).label("total_eligible"),
                    func.sum(
                        case(
                            (InterventionOutcome.outcome == "improved", 1),
                            else_=0,
                        )
                    ).label("total_improved"),
                )
                .join(
                    InterventionOutcome,
                    Recommendation.cbm_id == InterventionOutcome.cbm_id,
                )
                .filter(*conditions)
                .group_by(
                    Recommendation.recommendation_key,
                    Recommendation.recommendation_type,
                )
                .all()
            )

            results = []
            for row in rows:
                total_eligible = row.total_eligible or 0
                total_improved = row.total_improved or 0
                success_rate   = (
                    total_improved / total_eligible
                    if total_eligible > 0
                    else None
                )
                results.append({
                    "recommendation_key":    row.recommendation_key,
                    "recommendation_type":   row.recommendation_type,
                    "total_eligible":        total_eligible,
                    "total_improved":        total_improved,
                    "success_rate":          success_rate,
                    "has_sufficient_sample": total_eligible >= min_sample,
                })
            return results

        except Exception as exc:
            logger.warning("get_success_rates failed: %s", exc)
            return []

    def get_ranked_keys(
        self,
        db: Session,
        candidates: list[str],
        *,
        dimension:  Optional[str] = None,
        risk_level: Optional[str] = None,
        min_sample: int = 10,
    ) -> list[str]:
        """Return candidates sorted by descending success_rate.

        Keys with has_sufficient_sample=True are ranked first, ordered by
        success_rate descending.  Keys with insufficient sample or no data
        are appended after the ranked group in their original candidate order.
        No candidates are ever removed from the result.

        Returns the original candidate list on any exception.
        """
        try:
            rates = self.get_success_rates(
                db,
                dimension=dimension,
                risk_level=risk_level,
                min_sample=min_sample,
            )

            # Build a lookup of sufficient-sample keys → success_rate.
            # success_rate is always a float when has_sufficient_sample=True
            # because total_eligible >= min_sample >= 1 guarantees non-zero.
            ranked_lookup: dict[str, float] = {
                r["recommendation_key"]: r["success_rate"]
                for r in rates
                if r["has_sufficient_sample"]
            }

            ranked   = sorted(
                [k for k in candidates if k in ranked_lookup],
                key=lambda k: ranked_lookup[k],
                reverse=True,
            )
            unranked = [k for k in candidates if k not in ranked_lookup]
            return ranked + unranked

        except Exception as exc:
            logger.warning("get_ranked_keys failed: %s", exc)
            return list(candidates)
