"""Adaptive Recommendation Service.

Selects the best recommendation_key for a given trigger context by combining
governance-controlled candidate pools with historical success-rate data.

Pool lookup
───────────
For each trigger context (trigger_type, dimension), the service reads one row
from AI_ChatBot_RecommendationCandidatePools.  The row supplies:
  - candidate_keys_json  — ordered list of eligible recommendation_key strings
  - epsilon_override     — exploration probability (NULL → system default 0.05)
  - min_sample_override  — minimum outcomes for ranking eligibility (NULL → 10)

If no active pool row exists for the (trigger_type, dimension) pair, the
caller-supplied fallback_key is returned without modification.

Epsilon-greedy strategy
───────────────────────
  draw = random.random()
  if draw < epsilon:
      selected = random.choice(candidates)   # exploration — uniform over pool
  else:
      selected = ranked[0]                   # exploitation — highest success rate

Exploration samples uniformly from the full candidate list so every key
accumulates outcome data over time, preventing permanent neglect of untried
strategies.

Defensive contract
──────────────────
All failures are caught, logged at WARNING level, and resolved by returning
the caller-supplied fallback_key.  This method never raises.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Optional

from sqlalchemy.orm import Session

from services.models import RecommendationCandidatePool
from services.recommendation_learning_service import RecommendationLearningService

logger = logging.getLogger(__name__)

_DEFAULT_EPSILON:    float = 0.05
_DEFAULT_MIN_SAMPLE: int   = 10


class AdaptiveRecommendationService:
    """Selects a recommendation_key using evidence-driven epsilon-greedy ranking.

    All public methods accept a db Session as their first parameter.
    The session is used read-only; no commits or rollbacks are issued.
    """

    def select_key(
        self,
        db: Session,
        trigger_type: str,
        dimension: str,
        risk_level: Optional[str],
        fallback_key: str,
    ) -> str:
        """Return the best recommendation_key for the given trigger context.

        Parameters
        ----------
        db           SQLAlchemy Session — read-only; no commits issued.
        trigger_type Matches RecommendationCandidatePool.trigger_type.
        dimension    Matches RecommendationCandidatePool.dimension.
        risk_level   Passed to get_ranked_keys() for success-rate filtering.
        fallback_key Returned unchanged when no pool exists or any error occurs.

        Returns
        -------
        str — a recommendation_key from the pool, or fallback_key on failure.
        """
        try:
            # 1. Load pool
            pool = (
                db.query(RecommendationCandidatePool)
                .filter(
                    RecommendationCandidatePool.trigger_type == trigger_type,
                    RecommendationCandidatePool.dimension    == dimension,
                    RecommendationCandidatePool.is_active    == True,  # noqa: E712
                )
                .first()
            )
            if pool is None:
                return fallback_key

            # 2. Parse candidate keys
            try:
                candidates: list[str] = json.loads(pool.candidate_keys_json or "[]")
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "AdaptiveRecommendationService.select_key: "
                    "malformed candidate_keys_json for trigger_type=%r dimension=%r: %s",
                    trigger_type, dimension, exc,
                )
                return fallback_key

            if not candidates:
                logger.warning(
                    "AdaptiveRecommendationService.select_key: "
                    "empty candidate pool for trigger_type=%r dimension=%r — "
                    "returning fallback_key",
                    trigger_type, dimension,
                )
                return fallback_key

            # 3. Resolve per-pool adaptive parameters
            epsilon = (
                pool.epsilon_override
                if pool.epsilon_override is not None
                else _DEFAULT_EPSILON
            )
            min_sample = (
                pool.min_sample_override
                if pool.min_sample_override is not None
                else _DEFAULT_MIN_SAMPLE
            )

            # 4. Rank candidates by historical success rate
            ranked = RecommendationLearningService().get_ranked_keys(
                db,
                candidates,
                dimension=dimension,
                risk_level=risk_level,
                min_sample=min_sample,
            )

            # 5. Epsilon-greedy selection
            # ranked is guaranteed non-empty when candidates is non-empty:
            # get_ranked_keys() returns list(candidates) on any exception and
            # never drops a candidate from the output.
            if random.random() < epsilon:
                return random.choice(candidates)  # exploration
            return ranked[0]                      # exploitation

        except Exception as exc:
            logger.warning(
                "AdaptiveRecommendationService.select_key: unexpected error "
                "for trigger_type=%r dimension=%r — returning fallback_key: %s",
                trigger_type, dimension, exc,
            )
            return fallback_key
