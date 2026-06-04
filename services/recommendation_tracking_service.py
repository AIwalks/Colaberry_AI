"""Recommendation Tracking Service.

Records and invalidates AI-generated recommendations in
AI_ChatBot_Recommendations.

Design
──────
- One row per (cbm_id, recommendation_key) when is_active=True.
- Idempotent record() calls return the existing active row without inserting
  a duplicate.
- Invalidated rows (is_active=False) do not block a new record() for the same
  (cbm_id, recommendation_key).

Context serialization
─────────────────────
recommendation_context_json is NOT NULL in the schema.  _serialize_context()
converts unsupported value types to their string representations rather than
silently discarding the context.  Only a catastrophic serialization failure
(e.g. circular reference) falls back to '{}', and that is logged explicitly.

Defensive contract
──────────────────
All public methods are non-fatal.  Any exception is caught, logged, and the
method returns None / returns without side-effects.  Callers are never
affected by tracking failures.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from services.models import Recommendation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context serialization
# ---------------------------------------------------------------------------

class _SafeEncoder(json.JSONEncoder):
    """Encode non-serializable types as strings rather than raising.

    Priority:
      datetime  → ISO-8601 string
      Decimal   → float
      anything  → str(obj)
    """

    def default(self, obj: object) -> object:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        try:
            return str(obj)
        except Exception:
            return "<unserializable>"


def _serialize_context(context: dict) -> str:
    """Serialize context dict to a JSON string.

    Converts unsupported value types to strings to preserve as much context
    as possible.  Falls back to '{}' only when serialization fails entirely
    (e.g. circular reference); that fallback is always logged.
    """
    try:
        return json.dumps(context, cls=_SafeEncoder)
    except Exception as exc:
        logger.warning(
            "Recommendation context serialization failed — storing '{}': %s", exc
        )
        return "{}"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RecommendationTrackingService:
    """Records and invalidates AI-generated recommendations.

    All public methods accept a db Session as their first parameter and
    commit within the method body.  The session is never stored on the
    instance.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        db: Session,
        *,
        cbm_id: int,
        interpretation_id: Optional[int],
        entity_id: str,
        recommendation_type: str,
        recommendation_key: str,
        recommendation_text: str,
        dimension: str,
        risk_level: str,
        confidence: float,
        recommendation_context: dict,
        generated_by: str,
        model_name: Optional[str] = None,
    ) -> Optional[Recommendation]:
        """Insert one Recommendation row and return it.

        Idempotent: if an active row already exists for (cbm_id,
        recommendation_key), return it without inserting a duplicate.

        Returns None on any exception so that callers are never affected
        by a tracking failure.
        """
        try:
            existing = (
                db.query(Recommendation)
                .filter(
                    Recommendation.cbm_id == cbm_id,
                    Recommendation.recommendation_key == recommendation_key,
                    Recommendation.is_active == True,
                )
                .first()
            )
            if existing is not None:
                return existing

            row = Recommendation(
                cbm_id                      = cbm_id,
                interpretation_id           = interpretation_id,
                entity_id                   = entity_id,
                recommendation_type         = recommendation_type,
                recommendation_key          = recommendation_key,
                recommendation_text         = recommendation_text,
                dimension                   = dimension,
                risk_level                  = risk_level,
                confidence                  = confidence,
                recommendation_context_json = _serialize_context(recommendation_context),
                generated_by                = generated_by,
                model_name                  = model_name,
                is_active                   = True,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

        except Exception as exc:
            logger.warning(
                "Recommendation tracking failed for cbm_id=%s key=%r: %s",
                cbm_id,
                recommendation_key,
                exc,
            )
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def invalidate(
        self,
        db: Session,
        *,
        cbm_id: int,
        recommendation_key: str,
        reason: str,
    ) -> None:
        """Mark the active recommendation for (cbm_id, recommendation_key)
        as inactive.

        No-op when no matching active row exists.
        Non-fatal on any exception.
        """
        try:
            row = (
                db.query(Recommendation)
                .filter(
                    Recommendation.cbm_id == cbm_id,
                    Recommendation.recommendation_key == recommendation_key,
                    Recommendation.is_active == True,
                )
                .first()
            )
            if row is None:
                return

            row.is_active           = False
            row.invalidated_at      = datetime.utcnow()
            row.invalidation_reason = reason
            db.commit()

        except Exception as exc:
            logger.warning(
                "Recommendation invalidation failed for cbm_id=%s key=%r: %s",
                cbm_id,
                recommendation_key,
                exc,
            )
            try:
                db.rollback()
            except Exception:
                pass
