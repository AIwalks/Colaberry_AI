"""Deterministic trigger-type mapping (no I/O, no external calls)."""

from datetime import datetime

from sqlalchemy import select

from services.engagement_tracker_service import EngagementTrackerService

# ---------------------------------------------------------------------------
# Action map — (trigger_type, trigger_level) → actions_planned
# Used by TriggerEvaluator._actions_for() and kept here alongside _TRIGGER_MAP
# so all deterministic mappings live in one place.
# ---------------------------------------------------------------------------
_ACTION_MAP: dict[tuple[str, str], list[str]] = {
    # Stub types — retained for existing unit tests
    ("nudge_needed",        "Low"):     ["queue_nudge_message"],
    ("nudge_needed",        "High"):    ["queue_nudge_message"],
    ("nudge_needed",        "Unknown"): ["queue_nudge_message"],
    ("progress_milestone",  "Low"):     ["queue_congrats_message"],
    ("progress_milestone",  "High"):    ["queue_congrats_message"],
    ("progress_milestone",  "Unknown"): ["queue_congrats_message"],
    # Real TriggerType values from AI_ChatBot_TriggerRules
    ("All",               "Low"):     ["queue_outbound_message"],
    ("All",               "High"):    ["queue_outbound_message"],
    ("All",               "Unknown"): ["queue_outbound_message"],
    ("Capstone",          "Low"):     ["queue_outbound_message"],
    ("Capstone",          "High"):    ["queue_outbound_message"],
    ("Capstone",          "Unknown"): ["queue_outbound_message"],
    ("InClass",           "Low"):     ["queue_outbound_message"],
    ("InClass",           "High"):    ["queue_outbound_message"],
    ("InClass",           "Unknown"): ["queue_outbound_message"],
    ("InterviewPast4Wks", "Low"):     ["queue_outbound_message"],
    ("InterviewPast4Wks", "High"):    ["queue_outbound_message"],
    ("InterviewPast4Wks", "Unknown"): ["queue_outbound_message"],
    ("InterviewPrep",     "Low"):     ["queue_outbound_message"],
    ("InterviewPrep",     "High"):    ["queue_outbound_message"],
    ("InterviewPrep",     "Unknown"): ["queue_outbound_message"],
    ("IPBC",              "Low"):     ["queue_outbound_message"],
    ("IPBC",              "High"):    ["queue_outbound_message"],
    ("IPBC",              "Unknown"): ["queue_outbound_message"],
    ("PostInterview",     "Low"):     ["queue_outbound_message"],
    ("PostInterview",     "High"):    ["queue_outbound_message"],
    ("PostInterview",     "Unknown"): ["queue_outbound_message"],
}


class TriggerEvaluator:
    """Pure evaluation logic — no I/O, no DB, no session.

    Accepts plain ORM objects (or duck-typed fakes) as parameters so that
    unit tests can pass hand-crafted objects without touching a database.

    Methods
    -------
    evaluate(rule, student, event_id)
        Top-level entry point. Returns a result dict ready for the API
        response and for populating a TriggeredUser row.

    _get_kpi_value(student, kpi)
        Reads the named KPI attribute off the student object via getattr.

    _compute_level(value, rule)
        Compares the KPI value against TriggerLow / TriggerHigh thresholds.

    _actions_for(trigger_type, level)
        Maps (trigger_type, level) → list of action identifiers.
    """

    def evaluate(self, rule, student, event_id: str) -> dict:
        """Evaluate a single rule against a student and return a result dict.

        Parameters
        ----------
        rule    : TriggerRule ORM object or duck-typed fake.
        student : TriggerData ORM object, duck-typed fake, or None.
        event_id: Echoed from the original API request.

        Returns
        -------
        dict with keys: event_id, trigger_level, actions_planned, notes.
        """
        kpi_value = self._get_kpi_value(student, rule.KPI)
        trigger_level = self._compute_level(kpi_value, rule)
        actions = self._actions_for(rule.TriggerType, trigger_level)

        notes = (
            f"Rule CB_ID={rule.CB_ID} matched. "
            f"KPI={rule.KPI} value={kpi_value} level={trigger_level}."
        )

        return {
            "event_id":       event_id,
            "trigger_level":  trigger_level,
            "actions_planned": actions,
            "notes":          notes,
        }

    def _get_kpi_value(self, student, kpi: str | None) -> float | None:
        """Read the KPI column value off the student object.

        Uses getattr so the method works with both real ORM objects and fakes.
        Returns None if student is None, kpi is None/empty, or the attribute
        does not exist on the student object.
        """
        if student is None or not kpi:
            return None
        raw = getattr(student, kpi, None)
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _compute_level(self, value: float | None, rule) -> str:
        """Compare value against rule thresholds.

        Returns
        -------
        "Low"     — value is strictly below TriggerLow
        "High"    — value is strictly above TriggerHigh
        "Unknown" — value is None or both thresholds are absent
        "None"    — value is within the [TriggerLow, TriggerHigh] range
        """
        if value is None:
            return "Unknown"

        low = float(rule.TriggerLow) if rule.TriggerLow is not None else None
        high = float(rule.TriggerHigh) if rule.TriggerHigh is not None else None

        if low is None and high is None:
            return "Unknown"
        if low is not None and value < low:
            return "Low"
        if high is not None and value > high:
            return "High"
        return "None"

    def _actions_for(self, trigger_type: str | None, level: str) -> list[str]:
        """Map (trigger_type, level) → deterministic list of action identifiers.

        Returns an empty list for unrecognised combinations so callers always
        receive a list and never need to guard for None.
        """
        if trigger_type is None:
            return []
        return _ACTION_MAP.get((trigger_type, level), [])


# ---------------------------------------------------------------------------
# Original stub-based service — unchanged, all existing tests still apply.
# ---------------------------------------------------------------------------

_TRIGGER_MAP = {
    "nudge_needed": {
        "accepted": True,
        "actions_planned": ["queue_nudge_message"],
        "notes": "Nudge action planned (deterministic rule).",
    },
    "progress_milestone": {
        "accepted": True,
        "actions_planned": ["queue_congrats_message"],
        "notes": "Congrats action planned (deterministic rule).",
    },
}

_UNKNOWN = {
    "accepted": False,
    "actions_planned": [],
    "notes": "Unknown trigger type. No actions planned.",
}


class TriggerProcessingService:

    def process(self, payload: dict) -> dict:
        trigger_type = payload.get("trigger_type", "")
        result = _TRIGGER_MAP.get(trigger_type, _UNKNOWN)
        return {"event_id": payload["event_id"], **result}


# ---------------------------------------------------------------------------
# DB-backed service — reads rules from SQL Server, writes fired events.
# ---------------------------------------------------------------------------

class DbTriggerProcessingService:
    """DB-backed trigger processor.

    Replaces TriggerProcessingService once MSSQL_DATABASE_URL is configured.
    Reads rules from AI_ChatBot_TriggerRules, evaluates them via TriggerEvaluator,
    and writes the fired event to AI_ChatBot_TriggeredUsers.
    """

    def process(self, payload: dict) -> dict:
        from config.database import SessionLocal
        from services.models import TriggerData, TriggerRule, TriggeredUser

        if SessionLocal is None:
            raise RuntimeError(
                "DbTriggerProcessingService requires MSSQL_DATABASE_URL to be set."
            )

        trigger_type = payload.get("trigger_type", "")
        student_id   = payload.get("student_id", "")
        event_id     = payload.get("event_id", "")

        with SessionLocal() as session:
            # 1. Look up the matching rule
            rule: TriggerRule | None = (
                session.execute(
                    select(TriggerRule).where(TriggerRule.TriggerType == trigger_type)
                )
                .scalars()
                .first()
            )

            if rule is None:
                return {
                    "event_id":       event_id,
                    "accepted":       False,
                    "actions_planned": [],
                    "notes":          f"No rule found for trigger_type={trigger_type!r}.",
                }

            # 2. Look up the student (None is handled gracefully by TriggerEvaluator)
            try:
                user_id = int(student_id)
            except (ValueError, TypeError):
                user_id = None

            student: TriggerData | None = (
                session.get(TriggerData, user_id) if user_id is not None else None
            )

            # 3. Evaluate — pure, no I/O
            eval_result = TriggerEvaluator().evaluate(rule, student, event_id)

            # 4. Persist the fired event
            triggered = TriggeredUser(
                CB_ID        = rule.CB_ID,
                UserID       = user_id,
                TriggerType  = rule.TriggerType,
                TriggerLevel = eval_result["trigger_level"],
                KPI          = rule.KPI,
                Severity     = rule.Severity,
                InsertDate   = datetime.utcnow(),
                Completed    = 0,
                AgentID      = rule.AgentID,
            )
            session.add(triggered)
            session.commit()

        # 5. Log engagement event — must never stop trigger processing
        if isinstance(event_id, int):
            safe_trigger_id = event_id
        elif isinstance(event_id, str) and event_id.isdigit():
            safe_trigger_id = int(event_id)
        else:
            safe_trigger_id = None

        try:
            EngagementTrackerService().log_event(
                user_id    = user_id,
                event_type = "trigger",
                channel    = None,
                message    = f"Trigger {trigger_type} level {eval_result['trigger_level']}",
                agent_name = "TriggerProcessingService",
                trigger_id = safe_trigger_id,
            )
        except Exception:
            pass

        return {
            "event_id":        event_id,
            "accepted":        True,
            "actions_planned": eval_result["actions_planned"],
            "notes":           eval_result["notes"],
        }
