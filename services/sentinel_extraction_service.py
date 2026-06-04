"""Sentinel Extraction Layer.

Extracts real student intelligence signals from the database and normalizes
them into Sentinel dimension structures for downstream AI evaluation.

Read-only contract
──────────────────
This service issues SELECT queries only. No INSERT, UPDATE, or DELETE
reaches any table through this code path. Production data is never modified.
All downstream writes (interpretations, engagement events, governance records)
live in separate services that are never imported here.

Why normalization happens here, not in the AI layer
────────────────────────────────────────────────────
Raw rows speak the database's language: nullable integers, production column
names like `Past10DaysLogon`, status codes like `ActiveStatus="Y"`. The AI
evaluation layer expects clean, labeled, semantically consistent signals with
units and confidence scores. Normalizing here creates a stable schema contract:
if TriggerData gains a column or changes a name, only this file changes.

Shadow-mode safety
──────────────────
Because this service has no write path, it can run in shadow mode alongside
production indefinitely. Operators observe extraction outputs against real
mentor decisions to validate signal accuracy before enabling AI-driven actions.
A bug here surfaces as a wrong number on a report — not a wrong message to a
student.

V1 Sentinel dimensions implemented
───────────────────────────────────
  engagement                — login cadence, activity recency, attendance
  retention_risk            — assignment debt, grade trajectory, payment posture
  communication_responsiveness — chatbot response rate, channel activity
  intervention_effectiveness   — trigger completion rate, delivery success rate

Public API
──────────
  SentinelExtractionService.extract_student_state(db, entity_id, entity_type)
  → dict  (see _EMPTY_STATE for the guaranteed output shape)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from services.models import (
    BehaviorFingerprint,
    ChatBotAuditLog,
    ConversationState,
    DeliveryLog,
    EngagementEvent,
    TriggerData,
    TriggeredUser,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk inference thresholds (deterministic, no AI)
# ---------------------------------------------------------------------------

# engagement: days since last recorded activity
_ENGAGEMENT_CRITICAL_DAYS = 14
_ENGAGEMENT_HIGH_DAYS     = 7
_ENGAGEMENT_MEDIUM_DAYS   = 3

# retention_risk: number of assignments behind
_RETENTION_CRITICAL_HW_BEHIND = 5
_RETENTION_HIGH_HW_BEHIND     = 3
_RETENTION_MEDIUM_HW_BEHIND   = 1

# communication_responsiveness: completion rate (0.0–1.0)
_COMM_LOW_RATE_THRESHOLD    = 0.50   # below this → medium risk
_COMM_CRITICAL_RATE         = 0.0    # zero completions → high (not critical; no data for critical)

# intervention_effectiveness: delivery success rate
_INTERVENTION_LOW_RATE      = 0.50   # below this → medium risk
_INTERVENTION_CRITICAL_RATE = 0.0    # zero successes → high


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any, default: float = 0.0) -> float:
    """Cast to float, returning default on None or non-numeric."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """Cast to int, returning default on None or non-numeric."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _data_confidence(present: int, total: int) -> float:
    """Fraction of expected signals that are non-null. Clamped to [0.0, 1.0]."""
    if total == 0:
        return 0.0
    return max(0.0, min(1.0, present / total))


def _empty_dimension(notes: str = "No data available.") -> dict[str, Any]:
    """Safe default returned when a table has no row for this entity."""
    return {
        "signals":            [],
        "risk_level":         "unknown",
        "confidence":         0.0,
        "fingerprints":       [],
        "data_available":     False,
        "source_record_count": 0,
        "notes":              notes,
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SentinelExtractionService:
    """Extracts and normalizes student state from production-style tables.

    Parameters
    ----------
    use_mock:
        When True, ``extract_student_state`` returns synthetic data without
        touching the database. Defaults to False so existing callers and tests
        are unaffected. Set to True when MSSQL is not configured or
        SENTINEL_LIVE is False.
    """

    def __init__(self, use_mock: bool = False) -> None:
        self._use_mock = use_mock

    # ------------------------------------------------------------------
    # Mock state builder
    # ------------------------------------------------------------------

    def _build_mock_state(self, entity_id: str, entity_type: str) -> dict[str, Any]:
        """Return a realistic synthetic extraction result for shadow-mode testing."""
        extracted_at = datetime.utcnow().isoformat()
        _mock_dimensions: dict[str, dict[str, Any]] = {
            "engagement": {
                "signals": [
                    {"name": "last_activity_days",   "value": 5,    "unit": "days",    "confidence": 0.95},
                    {"name": "last_login_days",       "value": 3,    "unit": "days",    "confidence": 0.90},
                    {"name": "past_10_days_logon",    "value": 4,    "unit": "count",   "confidence": 0.85},
                    {"name": "attendance_percentage", "value": 72.5, "unit": "percent", "confidence": 0.85},
                ],
                "risk_level":          "medium",
                "confidence":          0.89,
                "fingerprints":        [],
                "data_available":      True,
                "source_record_count": 1,
                "notes":               "Mock data — MSSQL not configured or shadow mode inactive.",
            },
            "retention_risk": {
                "signals": [
                    {"name": "homeworks_behind", "value": 2,    "unit": "count", "confidence": 0.95},
                    {"name": "avg_hw_score",     "value": 68.0, "unit": "score", "confidence": 0.90},
                    {"name": "submission_rate",  "value": 0.75, "unit": "ratio", "confidence": 0.90},
                ],
                "risk_level":          "medium",
                "confidence":          0.85,
                "fingerprints":        [],
                "data_available":      True,
                "source_record_count": 1,
                "notes":               "Mock data — MSSQL not configured or shadow mode inactive.",
            },
            "communication_responsiveness": {
                "signals": [
                    {"name": "total_triggers_fired",     "value": 6,    "unit": "count", "confidence": 0.95},
                    {"name": "triggers_completed",       "value": 4,    "unit": "count", "confidence": 0.95},
                    {"name": "trigger_completion_rate",  "value": 0.67, "unit": "ratio", "confidence": 0.90},
                    {"name": "inbound_message_count",    "value": 3,    "unit": "count", "confidence": 0.85},
                    {"name": "outbound_message_count",   "value": 6,    "unit": "count", "confidence": 0.85},
                ],
                "risk_level":          "medium",
                "confidence":          0.82,
                "fingerprints":        [],
                "data_available":      True,
                "source_record_count": 7,
                "notes":               "Mock data — MSSQL not configured or shadow mode inactive.",
            },
            "intervention_effectiveness": {
                "signals": [
                    {"name": "total_interventions",           "value": 6,    "unit": "count", "confidence": 0.95},
                    {"name": "interventions_completed",       "value": 4,    "unit": "count", "confidence": 0.90},
                    {"name": "intervention_completion_rate",  "value": 0.67, "unit": "ratio", "confidence": 0.90},
                    {"name": "delivery_log_success_rate",     "value": 0.83, "unit": "ratio", "confidence": 0.90},
                    {"name": "positive_engagement_events",   "value": 3,    "unit": "count", "confidence": 0.80},
                ],
                "risk_level":          "low",
                "confidence":          0.88,
                "fingerprints":        [],
                "data_available":      True,
                "source_record_count": 10,
                "notes":               "Mock data — MSSQL not configured or shadow mode inactive.",
            },
        }
        signal_summary = self._build_signal_summary(_mock_dimensions)
        return {
            "entity_id":      entity_id,
            "entity_type":    entity_type,
            "dimensions":     _mock_dimensions,
            "source_tables":  ["mock"],
            "extracted_at":   extracted_at,
            "signal_summary": signal_summary,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_student_state(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
    ) -> dict[str, Any]:
        """Extract all V1 Sentinel dimensions for one entity.

        Parameters
        ----------
        db          SQLAlchemy session (read-only usage enforced internally).
                    Ignored when ``use_mock=True``.
        entity_id   String representation of the student identifier.
                    For entity_type="student" this maps to TriggerData.UserID.
        entity_type Semantic type label. Currently only "student" is supported;
                    other values return empty dimensions with data_available=False.

        Returns
        -------
        dict with keys: entity_id, entity_type, dimensions, source_tables,
        extracted_at, signal_summary.
        """
        if self._use_mock:
            logger.info(
                "SentinelExtraction: mock mode — returning synthetic state for entity_id=%r",
                entity_id,
            )
            return self._build_mock_state(entity_id, entity_type)

        extracted_at = datetime.utcnow().isoformat()
        logger.info(
            "SentinelExtraction: starting extraction for entity_id=%r entity_type=%r",
            entity_id, entity_type,
        )

        dimensions: dict[str, dict[str, Any]] = {}

        if entity_type != "student":
            logger.warning(
                "SentinelExtraction: entity_type=%r not supported in V1; "
                "returning empty dimensions.", entity_type,
            )
            for dim in ("engagement", "retention_risk",
                        "communication_responsiveness", "intervention_effectiveness"):
                dimensions[dim] = _empty_dimension(
                    f"entity_type={entity_type!r} not supported in V1."
                )
        else:
            dimensions["engagement"] = self._extract_engagement(
                db, entity_id, entity_type
            )
            dimensions["retention_risk"] = self._extract_retention_risk(
                db, entity_id, entity_type
            )
            dimensions["communication_responsiveness"] = (
                self._extract_communication_responsiveness(db, entity_id, entity_type)
            )
            dimensions["intervention_effectiveness"] = (
                self._extract_intervention_effectiveness(db, entity_id, entity_type)
            )

        signal_summary = self._build_signal_summary(dimensions)

        source_tables = [
            "AI_ChatBot_TriggerData",
            "AI_ChatBot_TriggeredUsers",
            "AI_ChatBot_BehaviorFingerprints",
            "AI_ChatBot_AuditLog",
            "AI_ChatBot_ConversationState",
            "AI_ChatBot_DeliveryLog",
            "AI_ChatBot_EngagementEvents",
        ]

        logger.info(
            "SentinelExtraction: completed for entity_id=%r — "
            "dimensions_with_data=%d highest_risk=%r",
            entity_id,
            signal_summary["dimensions_with_data"],
            signal_summary["highest_risk_level"],
        )

        return {
            "entity_id":      entity_id,
            "entity_type":    entity_type,
            "dimensions":     dimensions,
            "source_tables":  source_tables,
            "extracted_at":   extracted_at,
            "signal_summary": signal_summary,
        }

    # ------------------------------------------------------------------
    # Dimension extractors
    # ------------------------------------------------------------------

    def _extract_engagement(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
    ) -> dict[str, Any]:
        """Engagement dimension.

        Primary source: TriggerData (login cadence, activity recency, attendance).
        Secondary source: BehaviorFingerprint (engagement-tagged patterns).

        Risk inference is deterministic and based on LastActivityDays.
        Returns _empty_dimension when no TriggerData row exists.
        """
        try:
            user_id = int(entity_id)
        except (ValueError, TypeError):
            return _empty_dimension(
                f"entity_id={entity_id!r} is not a valid integer UserID."
            )

        row: Optional[TriggerData] = (
            db.query(TriggerData).filter(TriggerData.UserID == user_id).first()
        )

        if row is None:
            logger.info("SentinelExtraction[engagement]: no TriggerData row for UserID=%d", user_id)
            return _empty_dimension("No TriggerData row found for this student.")

        # Raw signal extraction
        last_activity_days   = row.LastActivityDays
        last_login_days      = row.LastLoginDays
        past_10_days_logon   = row.Past10DaysLogon
        attendance_pct       = row.AttendancePercentage
        days_in_status       = row.DaysInStatus
        is_class_active      = row.IsClassActive
        active_status        = row.ActiveStatus

        signals = [
            {
                "name":       "last_activity_days",
                "value":      last_activity_days,
                "unit":       "days",
                "confidence": 0.95 if last_activity_days is not None else 0.0,
            },
            {
                "name":       "last_login_days",
                "value":      last_login_days,
                "unit":       "days",
                "confidence": 0.90 if last_login_days is not None else 0.0,
            },
            {
                "name":       "past_10_days_logon",
                "value":      past_10_days_logon,
                "unit":       "count",
                "confidence": 0.85 if past_10_days_logon is not None else 0.0,
            },
            {
                "name":       "attendance_percentage",
                "value":      attendance_pct,
                "unit":       "percent",
                "confidence": 0.85 if attendance_pct is not None else 0.0,
            },
            {
                "name":       "days_in_status",
                "value":      days_in_status,
                "unit":       "days",
                "confidence": 0.80 if days_in_status is not None else 0.0,
            },
            {
                "name":       "is_class_active",
                "value":      bool(_safe_int(is_class_active, 0)),
                "unit":       "boolean",
                "confidence": 0.90 if is_class_active is not None else 0.0,
            },
            {
                "name":       "active_status",
                "value":      active_status,
                "unit":       "code",
                "confidence": 0.90 if active_status is not None else 0.0,
            },
        ]

        non_null = sum(1 for s in signals if s["value"] is not None)
        confidence = _data_confidence(non_null, len(signals))
        risk_level = self._infer_engagement_risk(last_activity_days, past_10_days_logon, active_status)

        fingerprints = self._load_fingerprints(db, entity_id, entity_type)

        return {
            "signals":            signals,
            "risk_level":         risk_level,
            "confidence":         round(confidence, 4),
            "fingerprints":       fingerprints,
            "data_available":     True,
            "source_record_count": 1,
            "notes":              (
                f"Extracted from TriggerData UserID={user_id}. "
                f"Risk inferred from LastActivityDays={last_activity_days}."
            ),
        }

    def _extract_retention_risk(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
    ) -> dict[str, Any]:
        """Retention risk dimension.

        Primary source: TriggerData (assignment debt, grade trajectory, payment).
        Secondary source: BehaviorFingerprint (risk-tagged patterns).

        Risk inference is deterministic and based on HWsBehind and AvgHWScore.
        """
        try:
            user_id = int(entity_id)
        except (ValueError, TypeError):
            return _empty_dimension(
                f"entity_id={entity_id!r} is not a valid integer UserID."
            )

        row: Optional[TriggerData] = (
            db.query(TriggerData).filter(TriggerData.UserID == user_id).first()
        )

        if row is None:
            return _empty_dimension("No TriggerData row found for this student.")

        hw_behind             = row.HWsBehind
        avg_hw_score          = row.AvgHWScore
        avg_eff_rating        = row.AvgEffRating
        assignments_submitted = row.NoOfAssignmentsSubmitted
        total_assignments     = row.TotalNoOfAssignments
        payment_balance       = row.PaymentBalance
        total_payments        = row.Total_Payments
        status_i              = row.StatusI
        status_ii             = row.StatusII

        submission_rate: Optional[float] = None
        if (
            total_assignments is not None
            and total_assignments > 0
            and assignments_submitted is not None
        ):
            submission_rate = round(assignments_submitted / total_assignments, 4)

        signals = [
            {
                "name":       "homeworks_behind",
                "value":      hw_behind,
                "unit":       "count",
                "confidence": 0.95 if hw_behind is not None else 0.0,
            },
            {
                "name":       "avg_hw_score",
                "value":      avg_hw_score,
                "unit":       "score",
                "confidence": 0.90 if avg_hw_score is not None else 0.0,
            },
            {
                "name":       "avg_effort_rating",
                "value":      avg_eff_rating,
                "unit":       "rating",
                "confidence": 0.85 if avg_eff_rating is not None else 0.0,
            },
            {
                "name":       "submission_rate",
                "value":      submission_rate,
                "unit":       "ratio",
                "confidence": 0.90 if submission_rate is not None else 0.0,
            },
            {
                "name":       "payment_balance",
                "value":      payment_balance,
                "unit":       "currency",
                "confidence": 0.80 if payment_balance is not None else 0.0,
            },
            {
                "name":       "total_payments",
                "value":      total_payments,
                "unit":       "currency",
                "confidence": 0.80 if total_payments is not None else 0.0,
            },
            {
                "name":       "status_i",
                "value":      status_i,
                "unit":       "code",
                "confidence": 0.85 if status_i is not None else 0.0,
            },
            {
                "name":       "status_ii_excerpt",
                "value":      (status_ii[:120] if isinstance(status_ii, str) else status_ii),
                "unit":       "text",
                "confidence": 0.70 if status_ii is not None else 0.0,
            },
        ]

        non_null = sum(1 for s in signals if s["value"] is not None)
        confidence = _data_confidence(non_null, len(signals))
        risk_level = self._infer_retention_risk(hw_behind, avg_hw_score, submission_rate)

        fingerprints = self._load_fingerprints(db, entity_id, entity_type)

        return {
            "signals":             signals,
            "risk_level":          risk_level,
            "confidence":          round(confidence, 4),
            "fingerprints":        fingerprints,
            "data_available":      True,
            "source_record_count": 1,
            "notes": (
                f"Extracted from TriggerData UserID={user_id}. "
                f"Risk inferred from HWsBehind={hw_behind}, AvgHWScore={avg_hw_score}."
            ),
        }

    def _extract_communication_responsiveness(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
    ) -> dict[str, Any]:
        """Communication responsiveness dimension.

        Primary sources:
          - TriggeredUser: completion rate of triggered communications
          - ChatBotAuditLog: inbound vs outbound message counts (via email/phone)
          - ConversationState: channel, recency of last interaction

        Risk inference: low trigger completion → poor responsiveness.
        """
        try:
            user_id = int(entity_id)
        except (ValueError, TypeError):
            return _empty_dimension(
                f"entity_id={entity_id!r} is not a valid integer UserID."
            )

        # Load TriggerData to get phone/email for ChatBotAuditLog join
        td_row: Optional[TriggerData] = (
            db.query(TriggerData).filter(TriggerData.UserID == user_id).first()
        )
        phone  = getattr(td_row, "PhoneNumber", None)
        email  = getattr(td_row, "Email", None)

        # TriggeredUser: completion metrics.
        # Explicit column selection avoids selecting DeliverySucceeded, which is added
        # by migration 0007 and is absent from SQL Server instances where that migration
        # has not been applied. A full db.query(TriggeredUser) would fail with
        # "Invalid column name 'DeliverySucceeded'" in those environments.
        triggered_rows = []
        try:
            triggered_rows = (
                db.query(
                    TriggeredUser.CBM_ID,
                    TriggeredUser.UserID,
                    TriggeredUser.Completed,
                    TriggeredUser.CompletedDate,
                )
                .filter(TriggeredUser.UserID == user_id)
                .all()
            )
        except Exception:
            logger.warning(
                "SentinelExtraction[communication]: AI_ChatBot_TriggeredUsers query failed "
                "for UserID=%d; continuing with empty trigger rows.", user_id,
            )
            try:
                db.rollback()
            except Exception:
                pass
        total_triggers   = len(triggered_rows)
        completed_count  = sum(
            1 for r in triggered_rows if _safe_int(getattr(r, "Completed", 0), 0) == 1
        )
        completion_rate: Optional[float] = (
            round(completed_count / total_triggers, 4) if total_triggers > 0 else None
        )

        # ChatBotAuditLog: message volume by direction
        audit_rows: list[ChatBotAuditLog] = []
        if phone or email:
            q = db.query(ChatBotAuditLog)
            if phone:
                q = q.filter(ChatBotAuditLog.phone_number == phone)
            elif email:
                q = q.filter(ChatBotAuditLog.Email == email)
            audit_rows = q.all()

        inbound_count  = sum(1 for r in audit_rows if r.entry_type == "incoming_message")
        outbound_count = sum(1 for r in audit_rows if r.entry_type == "outgoing_message")
        total_messages = len(audit_rows)

        # ConversationState
        conv: Optional[ConversationState] = None
        if phone:
            conv = (
                db.query(ConversationState)
                .filter(ConversationState.PhoneNumber == phone)
                .first()
            )
        channel      = getattr(conv, "Channel", None)
        last_updated = getattr(conv, "LastUpdated", None)
        last_updated_iso = last_updated.isoformat() if isinstance(last_updated, datetime) else last_updated

        signals = [
            {
                "name":       "total_triggers_fired",
                "value":      total_triggers,
                "unit":       "count",
                "confidence": 0.95 if total_triggers > 0 else 0.50,
            },
            {
                "name":       "triggers_completed",
                "value":      completed_count,
                "unit":       "count",
                "confidence": 0.95 if total_triggers > 0 else 0.50,
            },
            {
                "name":       "trigger_completion_rate",
                "value":      completion_rate,
                "unit":       "ratio",
                "confidence": 0.90 if completion_rate is not None else 0.0,
            },
            {
                "name":       "inbound_message_count",
                "value":      inbound_count,
                "unit":       "count",
                "confidence": 0.85 if total_messages > 0 else 0.40,
            },
            {
                "name":       "outbound_message_count",
                "value":      outbound_count,
                "unit":       "count",
                "confidence": 0.85 if total_messages > 0 else 0.40,
            },
            {
                "name":       "active_channel",
                "value":      channel,
                "unit":       "label",
                "confidence": 0.85 if channel is not None else 0.0,
            },
            {
                "name":       "last_conversation_updated",
                "value":      last_updated_iso,
                "unit":       "iso8601",
                "confidence": 0.80 if last_updated_iso is not None else 0.0,
            },
        ]

        data_available = total_triggers > 0 or total_messages > 0 or conv is not None
        non_null = sum(1 for s in signals if s["value"] is not None)
        confidence = _data_confidence(non_null, len(signals))
        risk_level = self._infer_communication_risk(completion_rate, total_triggers)

        return {
            "signals":             signals,
            "risk_level":          risk_level,
            "confidence":          round(confidence, 4),
            "fingerprints":        self._load_fingerprints(db, entity_id, entity_type),
            "data_available":      data_available,
            "source_record_count": total_triggers + total_messages + (1 if conv else 0),
            "notes": (
                f"total_triggers={total_triggers}, completed={completed_count}, "
                f"completion_rate={completion_rate}, "
                f"inbound={inbound_count}, outbound={outbound_count}, "
                f"channel={channel!r}."
            ),
        }

    def _extract_intervention_effectiveness(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
    ) -> dict[str, Any]:
        """Intervention effectiveness dimension.

        Primary sources:
          - TriggeredUser: completion rates (Completed=1 / CompletedDate set)
          - DeliveryLog: delivery success/failure rates per channel
          - EngagementEvent: event types that indicate positive engagement

        Risk inference: low delivery success or low completion → poor effectiveness.
        """
        try:
            user_id = int(entity_id)
        except (ValueError, TypeError):
            return _empty_dimension(
                f"entity_id={entity_id!r} is not a valid integer UserID."
            )

        # TriggeredUser — explicit column selection only.
        # DeliverySucceeded is intentionally excluded: it is added by migration 0007 and
        # is absent from SQL Server instances where that migration has not been applied.
        # A full db.query(TriggeredUser) generates "SELECT ... DeliverySucceeded ..." which
        # SQL Server rejects with "Invalid column name 'DeliverySucceeded'" in those envs.
        # Delivery success is inferred from Completed=1 OR CompletedDate IS NOT NULL instead.
        triggered_rows = []
        try:
            triggered_rows = (
                db.query(
                    TriggeredUser.CBM_ID,
                    TriggeredUser.UserID,
                    TriggeredUser.Completed,
                    TriggeredUser.CompletedDate,
                )
                .filter(TriggeredUser.UserID == user_id)
                .all()
            )
        except Exception:
            logger.warning(
                "SentinelExtraction[intervention]: AI_ChatBot_TriggeredUsers query failed "
                "for UserID=%d; continuing with empty trigger rows.", user_id,
            )
            try:
                db.rollback()
            except Exception:
                pass
        total_triggers  = len(triggered_rows)
        completed_count = sum(
            1 for r in triggered_rows if _safe_int(getattr(r, "Completed", 0), 0) == 1
        )
        cbm_ids = [r.CBM_ID for r in triggered_rows if r.CBM_ID is not None]

        # DeliveryLog: per-cbm_id success records
        delivery_rows: list[DeliveryLog] = []
        if cbm_ids:
            try:
                delivery_rows = (
                    db.query(DeliveryLog)
                    .filter(DeliveryLog.cbm_id.in_(cbm_ids))
                    .all()
                )
            except Exception:
                logger.warning(
                    "SentinelExtraction[intervention]: AI_ChatBot_DeliveryLog unavailable "
                    "for UserID=%d; continuing with empty delivery logs.", user_id,
                )
                try:
                    db.rollback()
                except Exception:
                    pass

        dl_success_count = sum(1 for r in delivery_rows if r.success is True)
        dl_fail_count    = sum(1 for r in delivery_rows if r.success is False)
        dl_total         = len(delivery_rows)
        dl_success_rate: Optional[float] = (
            round(dl_success_count / dl_total, 4) if dl_total > 0 else None
        )

        # Channels used
        channels_used = list({r.channel for r in delivery_rows if r.channel})

        # EngagementEvent: count of positive events for this user
        engagement_events: list[EngagementEvent] = []
        try:
            engagement_events = (
                db.query(EngagementEvent)
                .filter(EngagementEvent.user_id == user_id)
                .all()
            )
        except Exception:
            logger.warning(
                "SentinelExtraction[intervention]: AI_ChatBot_EngagementEvents unavailable "
                "for UserID=%d; continuing with empty events.", user_id,
            )
            try:
                db.rollback()
            except Exception:
                pass
        total_events      = len(engagement_events)
        positive_events   = sum(
            1 for e in engagement_events
            if e.event_type in ("nudge_sent", "trigger_fired", "response_received")
        )

        completion_rate: Optional[float] = (
            round(completed_count / total_triggers, 4) if total_triggers > 0 else None
        )

        signals = [
            {
                "name":       "total_interventions",
                "value":      total_triggers,
                "unit":       "count",
                "confidence": 0.95 if total_triggers > 0 else 0.50,
            },
            {
                "name":       "interventions_completed",
                "value":      completed_count,
                "unit":       "count",
                "confidence": 0.90 if total_triggers > 0 else 0.40,
            },
            {
                "name":       "intervention_completion_rate",
                "value":      completion_rate,
                "unit":       "ratio",
                "confidence": 0.90 if completion_rate is not None else 0.0,
            },
            {
                "name":       "delivery_log_success_rate",
                "value":      dl_success_rate,
                "unit":       "ratio",
                "confidence": 0.90 if dl_success_rate is not None else 0.0,
            },
            {
                "name":       "delivery_log_failures",
                "value":      dl_fail_count,
                "unit":       "count",
                "confidence": 0.85 if dl_total > 0 else 0.40,
            },
            {
                "name":       "channels_used",
                "value":      channels_used if channels_used else None,
                "unit":       "list",
                "confidence": 0.80 if channels_used else 0.0,
            },
            {
                "name":       "positive_engagement_events",
                "value":      positive_events,
                "unit":       "count",
                "confidence": 0.80 if total_events > 0 else 0.40,
            },
        ]

        data_available = total_triggers > 0 or dl_total > 0 or total_events > 0
        non_null = sum(1 for s in signals if s["value"] is not None)
        confidence = _data_confidence(non_null, len(signals))
        risk_level = self._infer_intervention_risk(completion_rate, dl_success_rate, total_triggers)

        return {
            "signals":             signals,
            "risk_level":          risk_level,
            "confidence":          round(confidence, 4),
            "fingerprints":        self._load_fingerprints(db, entity_id, entity_type),
            "data_available":      data_available,
            "source_record_count": total_triggers + dl_total + total_events,
            "notes": (
                f"total_triggers={total_triggers}, completed={completed_count}, "
                f"completion_rate={completion_rate}, "
                f"dl_success_rate={dl_success_rate}, "
                f"channels={channels_used!r}."
            ),
        }

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _load_fingerprints(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
    ) -> list[dict[str, Any]]:
        """Load BehaviorFingerprints for this entity. Returns [] on error."""
        try:
            rows: list[BehaviorFingerprint] = (
                db.query(BehaviorFingerprint)
                .filter(
                    BehaviorFingerprint.entity_id   == entity_id,
                    BehaviorFingerprint.entity_type == entity_type,
                )
                .all()
            )
            return [
                {
                    "pattern_name": r.pattern_name,
                    "score":        r.score,
                    "risk_level":   r.risk_level,
                }
                for r in rows
            ]
        except Exception:  # noqa: BLE001
            logger.warning(
                "SentinelExtraction: failed to load fingerprints for "
                "entity_id=%r entity_type=%r", entity_id, entity_type,
            )
            return []

    # ------------------------------------------------------------------
    # Risk inference (deterministic, threshold-based)
    # ------------------------------------------------------------------

    def _infer_engagement_risk(
        self,
        last_activity_days: Optional[int],
        past_10_days_logon: Optional[int],
        active_status: Optional[str],
    ) -> str:
        """Engagement risk from LastActivityDays and login cadence."""
        if last_activity_days is None and past_10_days_logon is None:
            return "unknown"
        if last_activity_days is not None:
            if last_activity_days >= _ENGAGEMENT_CRITICAL_DAYS:
                return "critical"
            if last_activity_days >= _ENGAGEMENT_HIGH_DAYS:
                return "high"
            if last_activity_days >= _ENGAGEMENT_MEDIUM_DAYS:
                return "medium"
        if past_10_days_logon is not None and past_10_days_logon == 0:
            return "high"
        return "low"

    def _infer_retention_risk(
        self,
        hw_behind: Optional[int],
        avg_hw_score: Optional[float],
        submission_rate: Optional[float],
    ) -> str:
        """Retention risk from assignment debt and grade trajectory."""
        if hw_behind is None and avg_hw_score is None and submission_rate is None:
            return "unknown"
        if hw_behind is not None:
            if hw_behind >= _RETENTION_CRITICAL_HW_BEHIND:
                return "critical"
            if hw_behind >= _RETENTION_HIGH_HW_BEHIND:
                return "high"
            if hw_behind >= _RETENTION_MEDIUM_HW_BEHIND:
                return "medium"
        # Secondary: very low submission rate as fallback escalator
        if submission_rate is not None and submission_rate < 0.40:
            return "high"
        return "low"

    def _infer_communication_risk(
        self,
        completion_rate: Optional[float],
        total_triggers: int,
    ) -> str:
        """Communication risk from trigger completion rate."""
        if total_triggers == 0:
            return "unknown"
        if completion_rate is None:
            return "unknown"
        if completion_rate <= _COMM_CRITICAL_RATE:
            return "high"
        if completion_rate < _COMM_LOW_RATE_THRESHOLD:
            return "medium"
        return "low"

    def _infer_intervention_risk(
        self,
        completion_rate: Optional[float],
        dl_success_rate: Optional[float],
        total_triggers: int,
    ) -> str:
        """Intervention effectiveness risk from delivery and completion rates."""
        if total_triggers == 0:
            return "unknown"
        # Delivery failure is the primary signal
        if dl_success_rate is not None:
            if dl_success_rate <= _INTERVENTION_CRITICAL_RATE:
                return "high"
            if dl_success_rate < _INTERVENTION_LOW_RATE:
                return "medium"
        # Fall back to completion rate
        if completion_rate is not None:
            if completion_rate <= _INTERVENTION_CRITICAL_RATE:
                return "high"
            if completion_rate < _INTERVENTION_LOW_RATE:
                return "medium"
        return "low"

    # ------------------------------------------------------------------
    # Summary builder
    # ------------------------------------------------------------------

    def _build_signal_summary(self, dimensions: dict[str, Any]) -> dict[str, Any]:
        """Aggregate across all four dimensions for a top-level status overview."""
        _RISK_ORDER = {"unknown": -1, "low": 0, "medium": 1, "high": 2, "critical": 3}

        total_signals       = sum(len(d.get("signals", [])) for d in dimensions.values())
        dimensions_with_data = sum(1 for d in dimensions.values() if d.get("data_available"))
        overall_confidence  = (
            sum(d.get("confidence", 0.0) for d in dimensions.values()) / len(dimensions)
            if dimensions else 0.0
        )

        highest_risk_dim   = "none"
        highest_risk_level = "unknown"
        highest_rank       = -1

        for dim_name, dim_data in dimensions.items():
            rl   = dim_data.get("risk_level", "unknown")
            rank = _RISK_ORDER.get(rl, -1)
            if rank > highest_rank:
                highest_rank       = rank
                highest_risk_level = rl
                highest_risk_dim   = dim_name

        return {
            "total_signals":           total_signals,
            "dimensions_with_data":    dimensions_with_data,
            "overall_confidence":      round(overall_confidence, 4),
            "highest_risk_dimension":  highest_risk_dim,
            "highest_risk_level":      highest_risk_level,
        }
