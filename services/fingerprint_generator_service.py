"""Sentinel Behavioral Fingerprint Generator.

Evaluates 4 deterministic rules against extracted student signals and writes
matching patterns to AI_ChatBot_BehaviorFingerprints.

Rules
─────
  stale_login_pattern      last_login_days >= 14
  stale_activity_pattern   last_activity_days >= 14
  low_trigger_completion   trigger_completion_rate < 0.25 AND total_triggers_fired >= 3
  active_but_disconnected  is_class_active AND active_status active AND last_activity_days >= 14

Dedup
─────
A rule is skipped if a matching (entity_id, entity_type, pattern_name) fingerprint
already exists within the last 24 hours.

Write contract
──────────────
Writes ONLY to AI_ChatBot_BehaviorFingerprints.
No reads from or writes to any production/core table.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.models import BehaviorFingerprint

logger = logging.getLogger(__name__)

_DEDUP_HOURS = 24
_STALE_THRESHOLD_DAYS = 14
_STALE_HIGH_DAYS = 21
_ACTIVE_STATUSES = frozenset({"active", "y", "a"})


# ---------------------------------------------------------------------------
# Pure rule evaluation (no DB, no side effects)
# ---------------------------------------------------------------------------

def _evaluate_rules(
    entity_id: str,
    entity_type: str,
    signals: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return candidate fingerprint dicts for every rule that fires.

    Each dict contains: entity_type, entity_id, pattern_name, score, risk_level,
    details_json.  Nothing is written to the DB here.
    """
    results: list[dict[str, Any]] = []

    last_login_days:         Any = signals.get("last_login_days")
    last_activity_days:      Any = signals.get("last_activity_days")
    is_class_active:         Any = signals.get("is_class_active")
    active_status:           Any = signals.get("active_status")
    trigger_completion_rate: Any = signals.get("trigger_completion_rate")
    total_triggers_fired:    Any = signals.get("total_triggers_fired")

    # Rule 1 — stale_login_pattern
    if last_login_days is not None and last_login_days >= _STALE_THRESHOLD_DAYS:
        score = min(1.0, last_login_days / 30.0)
        risk  = "high" if last_login_days >= _STALE_HIGH_DAYS else "medium"
        results.append({
            "entity_type":  entity_type,
            "entity_id":    entity_id,
            "pattern_name": "stale_login_pattern",
            "score":        score,
            "risk_level":   risk,
            "details_json": json.dumps({
                "last_login_days": last_login_days,
                "threshold":       _STALE_THRESHOLD_DAYS,
            }),
        })

    # Rule 2 — stale_activity_pattern
    if last_activity_days is not None and last_activity_days >= _STALE_THRESHOLD_DAYS:
        score = min(1.0, last_activity_days / 30.0)
        risk  = "high" if last_activity_days >= _STALE_HIGH_DAYS else "medium"
        results.append({
            "entity_type":  entity_type,
            "entity_id":    entity_id,
            "pattern_name": "stale_activity_pattern",
            "score":        score,
            "risk_level":   risk,
            "details_json": json.dumps({
                "last_activity_days": last_activity_days,
                "threshold":          _STALE_THRESHOLD_DAYS,
            }),
        })

    # Rule 3 — low_trigger_completion
    if (
        trigger_completion_rate is not None
        and total_triggers_fired is not None
        and total_triggers_fired >= 3
        and trigger_completion_rate < 0.25
    ):
        score = 1.0 - trigger_completion_rate
        results.append({
            "entity_type":  entity_type,
            "entity_id":    entity_id,
            "pattern_name": "low_trigger_completion",
            "score":        score,
            "risk_level":   "high",
            "details_json": json.dumps({
                "trigger_completion_rate": trigger_completion_rate,
                "total_triggers_fired":    total_triggers_fired,
                "threshold_rate":          0.25,
                "threshold_min_triggers":  3,
            }),
        })

    # Rule 4 — active_but_disconnected
    is_active_class = is_class_active in (1, True, "1", "true", "True")
    is_active_status = (
        isinstance(active_status, str)
        and active_status.strip().lower() in _ACTIVE_STATUSES
    )
    if (
        is_active_class
        and is_active_status
        and last_activity_days is not None
        and last_activity_days >= _STALE_THRESHOLD_DAYS
    ):
        score = min(1.0, last_activity_days / 30.0)
        results.append({
            "entity_type":  entity_type,
            "entity_id":    entity_id,
            "pattern_name": "active_but_disconnected",
            "score":        score,
            "risk_level":   "high",
            "details_json": json.dumps({
                "last_activity_days": last_activity_days,
                "is_class_active":    is_class_active,
                "active_status":      active_status,
                "threshold":          _STALE_THRESHOLD_DAYS,
            }),
        })

    return results


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class FingerprintGeneratorService:
    """Generates and persists behavioral fingerprints from extracted signals.

    Stateless — db is passed per-call.
    """

    def generate_and_persist(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
        extraction: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Evaluate rules and write new fingerprints to DB.

        Returns list of newly written fingerprint dicts (format matches what
        SentinelExtractionService._load_fingerprints returns so they can be
        appended to current_fingerprints directly).  Never raises — errors are
        logged and an empty list is returned.
        """
        signals    = self._flatten_signals(extraction)
        candidates = _evaluate_rules(entity_id, entity_type, signals)

        written: list[dict[str, Any]] = []
        for candidate in candidates:
            pattern_name = candidate["pattern_name"]
            try:
                if self._is_recent_duplicate(db, entity_id, entity_type, pattern_name):
                    logger.info(
                        "FingerprintGenerator[%s]: SKIP %r — duplicate within %dh",
                        entity_id, pattern_name, _DEDUP_HOURS,
                    )
                    continue

                record = BehaviorFingerprint(
                    entity_type  = candidate["entity_type"],
                    entity_id    = candidate["entity_id"],
                    pattern_name = candidate["pattern_name"],
                    score        = candidate["score"],
                    risk_level   = candidate["risk_level"],
                    details_json = candidate["details_json"],
                )
                db.add(record)
                db.commit()
                db.refresh(record)

                logger.info(
                    "FingerprintGenerator[%s]: WROTE %r score=%.3f risk=%r id=%s",
                    entity_id, pattern_name,
                    candidate["score"], candidate["risk_level"],
                    getattr(record, "id", None),
                )
                written.append({
                    "id":           getattr(record, "id", None),
                    "pattern_name": pattern_name,
                    "score":        candidate["score"],
                    "risk_level":   candidate["risk_level"],
                    "details_json": candidate["details_json"],
                })

            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "FingerprintGenerator[%s]: failed to write %r: %s",
                    entity_id, pattern_name, exc,
                )
                try:
                    db.rollback()
                except Exception:
                    pass

        logger.info(
            "FingerprintGenerator[%s]: done — %d candidates, %d written, %d skipped/failed",
            entity_id, len(candidates), len(written), len(candidates) - len(written),
        )
        return written

    @staticmethod
    def _flatten_signals(extraction: dict[str, Any]) -> dict[str, Any]:
        """Flatten all dimension signals into one dict keyed by signal name."""
        flat: dict[str, Any] = {}
        for dim_data in extraction.get("dimensions", {}).values():
            for sig in dim_data.get("signals", []):
                name = sig.get("name")
                if name:
                    flat[name] = sig.get("value")
        return flat

    @staticmethod
    def _is_recent_duplicate(
        db: Session,
        entity_id: str,
        entity_type: str,
        pattern_name: str,
    ) -> bool:
        """Return True if an identical fingerprint was written in the last 24 hours."""
        cutoff = datetime.utcnow() - timedelta(hours=_DEDUP_HOURS)
        count = (
            db.query(func.count(BehaviorFingerprint.id))
            .filter(
                BehaviorFingerprint.entity_id    == entity_id,
                BehaviorFingerprint.entity_type  == entity_type,
                BehaviorFingerprint.pattern_name == pattern_name,
                BehaviorFingerprint.created_at   >= cutoff,
            )
            .scalar()
        )
        return (count or 0) > 0
