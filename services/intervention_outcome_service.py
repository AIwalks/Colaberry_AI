"""Intervention Outcome Service.

Manages enrollment and evaluation of AI_ChatBot_InterventionOutcomes records.

Enrollment
──────────
enroll() creates one row per trigger in AI_ChatBot_InterventionOutcomes.
Called immediately after MentorMessageService writes DeliverySucceeded to
TriggeredUsers. Duplicate calls for the same cbm_id are safe no-ops — the
UNIQUE constraint on cbm_id is enforced at both the application and DB layers.

Evaluation
──────────
evaluate_ready_outcomes() scores pending records whose evaluation window has
closed (window_end <= utcnow()). Reads TriggerData.LastActivityDays as the
after-state and applies deterministic delta criteria to classify each record.

Outcome labels
──────────────
  improved      — after_last_activity_days < before by >= minimum_delta_days
  not_improved  — delivery succeeded but delta below threshold
  inconclusive  — delivery gate failed, before-state unknown, student already
                  healthy, or after-state could not be captured

Before-state source priority
─────────────────────────────
  1. AIInterpretation.source_snapshot_json  (preferred — immutable frozen snapshot)
  2. TriggerData.LastActivityDays           (live fallback at enrollment time)
  3. 'unavailable'                          (neither found — outcome will be inconclusive)

Defensive contract
──────────────────
All public methods are non-fatal. Any exception is logged and swallowed.
Callers are never affected by internal failures.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from services.models import AIInterpretation, InterventionOutcome, TriggerData

logger = logging.getLogger(__name__)

_HEALTHY_ACTIVITY_THRESHOLD: int = 3   # days; at or below this the student is already active
_DEFAULT_WINDOW_DAYS:        int = 14
_DEFAULT_MIN_DELTA:          int = 3   # minimum day improvement to classify as 'improved'


class InterventionOutcomeService:
    """Manages the InterventionOutcome lifecycle from enrollment to evaluation.

    All methods accept a db Session as their first parameter and commit within
    the method body. The session is never stored on the instance.
    """

    # ------------------------------------------------------------------
    # Public API — enrollment
    # ------------------------------------------------------------------

    def enroll(
        self,
        db: Session,
        cbm_id: int,
        user_id: Optional[int],
        delivery_succeeded: Optional[bool],
        window_start: datetime,
        evaluation_window_days: int = _DEFAULT_WINDOW_DAYS,
    ) -> Optional[InterventionOutcome]:
        """Create one InterventionOutcome row for the given trigger.

        Idempotent: if a row with this cbm_id already exists, returns the
        existing row without any modification.

        Parameters
        ----------
        cbm_id                  PK of the TriggeredUsers row being enrolled.
        user_id                 TriggeredUsers.UserID; nullable — rows with
                                UserID=NULL must still be enrolled.
        delivery_succeeded      TriggeredUsers.DeliverySucceeded value.
                                None (no delivery attempt) is treated as False.
        window_start            TriggeredUsers.InsertDate.
        evaluation_window_days  Length of the outcome window in days.

        Returns
        -------
        The created or pre-existing InterventionOutcome, or None on error.
        """
        try:
            # --- Dedup check -----------------------------------------------
            existing = (
                db.query(InterventionOutcome)
                .filter(InterventionOutcome.cbm_id == cbm_id)
                .first()
            )
            if existing is not None:
                logger.info(
                    "InterventionOutcomeService.enroll[cbm_id=%d]: already enrolled — skipping",
                    cbm_id,
                )
                return existing

            # --- Delivery gate ---------------------------------------------
            # None (no attempt made) is treated identically to False —
            # the gate is not passed in either case.
            gate_passed: bool = delivery_succeeded is True

            # --- Before-state resolution -----------------------------------
            before = self._resolve_before_state(db, user_id, window_start)

            # --- Create record ---------------------------------------------
            now = datetime.utcnow()
            record = InterventionOutcome(
                cbm_id                    = cbm_id,
                user_id                   = user_id,
                interpretation_id         = before["interpretation_id"],
                window_start              = window_start,
                window_end                = window_start + timedelta(days=evaluation_window_days),
                evaluation_window_days    = evaluation_window_days,
                delivery_gate_passed      = gate_passed,
                before_last_activity_days = before["before_last_activity_days"],
                before_risk_level         = before["before_risk_level"],
                before_snapshot_source    = before["before_snapshot_source"],
                outcome                   = "pending",
                eligible_for_learning     = None,
                created_at                = now,
                updated_at                = now,
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            logger.info(
                "InterventionOutcomeService.enroll[cbm_id=%d]: enrolled "
                "gate=%s before_activity=%s source=%r",
                cbm_id,
                gate_passed,
                before["before_last_activity_days"],
                before["before_snapshot_source"],
            )
            return record

        except Exception as exc:
            logger.error(
                "InterventionOutcomeService.enroll[cbm_id=%d]: failed: %s",
                cbm_id, exc,
            )
            try:
                db.rollback()
            except Exception:
                pass
            return None

    # ------------------------------------------------------------------
    # Public API — evaluation
    # ------------------------------------------------------------------

    def evaluate_ready_outcomes(
        self,
        db: Session,
        minimum_delta_days: int = _DEFAULT_MIN_DELTA,
    ) -> int:
        """Score all pending records whose evaluation window has closed.

        Queries for outcome='pending' AND window_end <= utcnow(). For each
        record, reads the current after-state from TriggerData and applies
        the deterministic classification criteria.

        Returns
        -------
        int — count of records transitioned out of 'pending' status.
              Returns 0 if the query fails or no records are ready.
        """
        now = datetime.utcnow()

        try:
            ready = (
                db.query(InterventionOutcome)
                .filter(
                    InterventionOutcome.outcome == "pending",
                    InterventionOutcome.window_end <= now,
                )
                .all()
            )
        except Exception as exc:
            logger.error(
                "InterventionOutcomeService.evaluate_ready_outcomes: query failed: %s", exc,
            )
            return 0

        if not ready:
            return 0

        evaluated = 0
        for record in ready:
            try:
                self._evaluate_one(db, record, minimum_delta_days, now)
                evaluated += 1
            except Exception as exc:
                logger.error(
                    "InterventionOutcomeService.evaluate_ready_outcomes"
                    "[cbm_id=%s]: failed: %s",
                    record.cbm_id, exc,
                )

        logger.info(
            "InterventionOutcomeService.evaluate_ready_outcomes: "
            "ready=%d evaluated=%d",
            len(ready), evaluated,
        )
        return evaluated

    # ------------------------------------------------------------------
    # Private — evaluation core
    # ------------------------------------------------------------------

    def _evaluate_one(
        self,
        db: Session,
        record: InterventionOutcome,
        minimum_delta_days: int,
        now: datetime,
    ) -> None:
        """Classify one pending record and write the outcome back to the DB.

        Inconclusive conditions are checked in priority order. The first
        matching condition sets the outcome and returns immediately.
        """
        # --- Inconclusive gate checks (order matters) ------------------

        if not record.delivery_gate_passed:
            self._write_outcome(
                db, record, now,
                outcome  = "inconclusive",
                reason   = (
                    "Delivery did not succeed — intervention did not reach "
                    "student; outcome not attributable"
                ),
                eligible = False,
            )
            return

        if record.before_last_activity_days is None:
            self._write_outcome(
                db, record, now,
                outcome  = "inconclusive",
                reason   = (
                    f"Before-state unavailable "
                    f"(source: {record.before_snapshot_source}) — baseline unknown"
                ),
                eligible = False,
            )
            return

        if record.before_last_activity_days <= _HEALTHY_ACTIVITY_THRESHOLD:
            self._write_outcome(
                db, record, now,
                outcome  = "inconclusive",
                reason   = (
                    f"Student was already in healthy activity range "
                    f"({record.before_last_activity_days} days) at trigger time — "
                    f"activity KPI cannot signal improvement"
                ),
                eligible = False,
            )
            return

        # --- Capture after-state ---------------------------------------

        after_activity = self._read_after_activity_days(db, record.user_id)
        after_risk     = self._read_after_risk_level(db, record.user_id, now)

        if after_activity is None:
            self._write_outcome(
                db, record, now,
                outcome          = "inconclusive",
                reason           = (
                    "After-state unavailable at evaluation time — "
                    "student may no longer be in system"
                ),
                eligible         = False,
                after_activity   = None,
                after_risk       = after_risk,
            )
            return

        # --- Classify outcome ------------------------------------------

        delta = record.before_last_activity_days - after_activity

        if delta >= minimum_delta_days:
            self._write_outcome(
                db, record, now,
                outcome        = "improved",
                reason         = (
                    f"Activity days decreased from "
                    f"{record.before_last_activity_days} to {after_activity} — "
                    f"improvement of {delta} days (threshold: {minimum_delta_days})"
                ),
                eligible       = True,
                after_activity = after_activity,
                after_risk     = after_risk,
            )
        else:
            self._write_outcome(
                db, record, now,
                outcome        = "not_improved",
                reason         = (
                    f"Activity days changed from "
                    f"{record.before_last_activity_days} to {after_activity} — "
                    f"improvement of {delta} days is below "
                    f"threshold ({minimum_delta_days})"
                ),
                eligible       = True,
                after_activity = after_activity,
                after_risk     = after_risk,
            )

    def _write_outcome(
        self,
        db: Session,
        record: InterventionOutcome,
        now: datetime,
        *,
        outcome: str,
        reason: str,
        eligible: Optional[bool],
        after_activity: Optional[int] = None,
        after_risk: Optional[str] = None,
    ) -> None:
        record.outcome               = outcome
        record.outcome_reason        = reason
        record.eligible_for_learning = eligible
        record.evaluated_at          = now
        record.updated_at            = now
        if after_activity is not None:
            record.after_last_activity_days = after_activity
            record.after_captured_at        = now
        if after_risk is not None:
            record.after_risk_level = after_risk
        db.commit()

    # ------------------------------------------------------------------
    # Private — before-state resolution
    # ------------------------------------------------------------------

    def _resolve_before_state(
        self,
        db: Session,
        user_id: Optional[int],
        window_start: datetime,
    ) -> dict[str, Any]:
        """Return before-state dict from the best available source.

        Priority:
          1. AIInterpretation.source_snapshot_json  (immutable, preferred)
          2. TriggerData.LastActivityDays           (live fallback)
          3. 'unavailable'                          (no source found)
        """
        result: dict[str, Any] = {
            "before_last_activity_days": None,
            "before_risk_level":         None,
            "interpretation_id":         None,
            "before_snapshot_source":    "unavailable",
        }

        if user_id is None:
            return result

        # 1 — AIInterpretation snapshot
        try:
            interp = (
                db.query(AIInterpretation)
                .filter(
                    AIInterpretation.entity_id == str(user_id),
                    AIInterpretation.is_active.is_(True),
                    AIInterpretation.created_at <= window_start,
                )
                .order_by(AIInterpretation.created_at.desc())
                .first()
            )
            if interp is not None:
                result["interpretation_id"] = interp.id
                result["before_risk_level"] = interp.risk_level
                activity = self._extract_activity_days_from_snapshot(
                    interp.source_snapshot_json or ""
                )
                if activity is not None:
                    result["before_last_activity_days"] = activity
                    result["before_snapshot_source"]    = "interpretation"
                    return result
                # Interpretation found but snapshot has no activity days — fall through
        except Exception as exc:
            logger.warning(
                "InterventionOutcomeService._resolve_before_state: "
                "AIInterpretation lookup failed: %s", exc,
            )

        # 2 — TriggerData live fallback
        try:
            td = (
                db.query(TriggerData)
                .filter(TriggerData.UserID == user_id)
                .first()
            )
            if td is not None and td.LastActivityDays is not None:
                result["before_last_activity_days"] = td.LastActivityDays
                result["before_snapshot_source"]    = "trigger_data"
                return result
        except Exception as exc:
            logger.warning(
                "InterventionOutcomeService._resolve_before_state: "
                "TriggerData lookup failed: %s", exc,
            )

        return result  # before_snapshot_source remains 'unavailable'

    def _read_after_activity_days(
        self,
        db: Session,
        user_id: Optional[int],
    ) -> Optional[int]:
        if user_id is None:
            return None
        try:
            td = (
                db.query(TriggerData)
                .filter(TriggerData.UserID == user_id)
                .first()
            )
            return td.LastActivityDays if td is not None else None
        except Exception as exc:
            logger.warning(
                "InterventionOutcomeService._read_after_activity_days: failed: %s", exc,
            )
            return None

    def _read_after_risk_level(
        self,
        db: Session,
        user_id: Optional[int],
        after_time: datetime,
    ) -> Optional[str]:
        if user_id is None:
            return None
        try:
            interp = (
                db.query(AIInterpretation)
                .filter(
                    AIInterpretation.entity_id == str(user_id),
                    AIInterpretation.is_active.is_(True),
                    AIInterpretation.created_at >= after_time,
                )
                .order_by(AIInterpretation.created_at.desc())
                .first()
            )
            return interp.risk_level if interp is not None else None
        except Exception as exc:
            logger.warning(
                "InterventionOutcomeService._read_after_risk_level: failed: %s", exc,
            )
            return None

    # ------------------------------------------------------------------
    # Private — snapshot parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_activity_days_from_snapshot(snapshot_json: str) -> Optional[int]:
        """Parse last_activity_days from AIInterpretation.source_snapshot_json.

        Handles both payload shapes produced by the orchestration layer:

          Shape A (orchestration payload):
            {"kpis": [{"kpi_name": "last_activity_days", "value": 18}, ...]}

          Shape B (extraction dimensions):
            {"dimensions": {"engagement": {"signals":
              [{"name": "last_activity_days", "value": 18}, ...]}}}
        """
        if not snapshot_json:
            return None
        try:
            data = json.loads(snapshot_json)
        except (json.JSONDecodeError, TypeError):
            return None

        # Shape A: flat kpis list
        for kpi in data.get("kpis", []):
            if kpi.get("kpi_name") == "last_activity_days":
                v = kpi.get("value")
                if v is not None:
                    try:
                        return int(v)
                    except (TypeError, ValueError):
                        pass

        # Shape B: nested dimensions → signals
        for dim_data in data.get("dimensions", {}).values():
            for sig in dim_data.get("signals", []):
                if sig.get("name") == "last_activity_days":
                    v = sig.get("value")
                    if v is not None:
                        try:
                            return int(v)
                        except (TypeError, ValueError):
                            pass

        return None
