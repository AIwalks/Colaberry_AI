"""Student response-to-trigger matcher services.

Two matching strategies defined in directives/student_response_tracking_contract.md:

  ThreadIdMatcher      — deterministic; confidence always 1.0  (directive §3, §5.1)
  TimeProximityMatcher — heuristic;    confidence capped at 0.7 (directive §3, §5.2)

CRITICAL (directive §9): matchers must run in a background process or scheduled job.
They must NEVER be invoked within the inbound request/response cycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from services.audit_log_service import AuditLogService
from services.models import EngagementEvent, StudentResponse, TriggeredUser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — directive §3, §5, §6
# ---------------------------------------------------------------------------

MATCH_METHOD_THREAD_ID:       str   = "thread_id"
MATCH_METHOD_TIME_PROXIMITY:  str   = "time_proximity"
MATCH_METHOD_MANUAL:          str   = "manual"

CONFIDENCE_DETERMINISTIC:         float = 1.0
CONFIDENCE_TIME_PROXIMITY_MAX:    float = 0.7   # hard ceiling; never exceeded by heuristic (§5.2, §6)

# Default window searched by TimeProximityMatcher.
# Override per-channel via TimeProximityMatcher(window_hours=...).
DEFAULT_WINDOW_HOURS:         float = 72.0

# Minimum confidence a single trigger must reach to be recorded.
# If no trigger meets this threshold, or two or more do, no row is created (§5.2).
# Placeholder — validate and adjust before production use.
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.3


# ---------------------------------------------------------------------------
# MatchResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MatchResult:
    """Immutable value returned by a successful match() call.

    Callers use this to construct and insert a StudentResponse row.
    match() returns None on no match — callers must NOT insert a row in that case.
    """
    cbm_id:              int
    engagement_event_id: int
    user_id:             int
    response_channel:    str
    match_method:        str
    confidence:          float
    matched_at:          datetime


# ---------------------------------------------------------------------------
# Persistence — directive §7, §8
# ---------------------------------------------------------------------------

def persist_match(session: Session, result: MatchResult) -> Optional[StudentResponse]:
    """Persist a MatchResult as a StudentResponse row, enforcing idempotency.

    Idempotency rules (directive §8):

      - No existing row for result.engagement_event_id:
          Insert a new StudentResponse, commit, return it.

      - Existing row with the SAME cbm_id:
          Duplicate call — log DEBUG, return the existing row unchanged.
          No second insert is created.

      - Existing row with a DIFFERENT cbm_id:
          Conflict — log WARNING, insert nothing, return None.
          The caller must use the manual override path (delete + insert with
          match_method="manual", confidence=1.0) to resolve (directive §8).

    This function never updates an existing row (append-only, directive §7).

    Args:
        session: Active SQLAlchemy session. Caller owns the session lifecycle.
        result:  MatchResult produced by ThreadIdMatcher or TimeProximityMatcher.

    Returns:
        The StudentResponse row (existing or newly inserted) on success.
        None when a cbm_id conflict blocks the insert.
    """
    existing: Optional[StudentResponse] = (
        session.query(StudentResponse)
        .filter(StudentResponse.engagement_event_id == result.engagement_event_id)
        .first()
    )

    if existing is not None:
        if existing.cbm_id == result.cbm_id:
            logger.debug(
                "persist_match: duplicate — engagement_event_id=%s cbm_id=%s already "
                "recorded; no insert.",
                result.engagement_event_id, result.cbm_id,
            )
            return existing

        logger.warning(
            "persist_match: conflict — engagement_event_id=%s already linked to "
            "cbm_id=%s; incoming cbm_id=%s blocked. Manual override required "
            "(directive §8).",
            result.engagement_event_id, existing.cbm_id, result.cbm_id,
        )
        return None

    row = StudentResponse(
        cbm_id              = result.cbm_id,
        engagement_event_id = result.engagement_event_id,
        user_id             = result.user_id,
        response_channel    = result.response_channel,
        match_method        = result.match_method,
        confidence          = result.confidence,
        matched_at          = result.matched_at,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    logger.debug(
        "persist_match: inserted StudentResponse id=%s "
        "engagement_event_id=%s cbm_id=%s match_method=%r confidence=%.3f.",
        row.id, result.engagement_event_id, result.cbm_id,
        result.match_method, result.confidence,
    )
    try:
        AuditLogService().log_event(
            phone_number            = None,
            entry_type              = "student_response_matched",
            input_message           = None,
            output_message          = (
                f"match_method={result.match_method} "
                f"confidence={result.confidence:.3f} "
                f"engagement_event_id={result.engagement_event_id}"
            ),
            cbm_id                  = result.cbm_id,
            email                   = None,
            channel                 = result.response_channel,
            processing_time_seconds = None,
        )
    except Exception:
        pass
    return row


# ---------------------------------------------------------------------------
# ThreadIdMatcher
# ---------------------------------------------------------------------------

class ThreadIdMatcher:
    """Deterministic response matcher using a channel-provided thread identifier.

    When a delivery channel echoes a thread_id on the outbound message and the
    student's reply carries the same identifier, the association is unambiguous.
    Confidence is always 1.0 on a successful match (directive §3, §5.1, §6).

    Resolution path (directive §5.1, corrected):
      Query EngagementEvent WHERE thread_id = ? AND user_id = ? AND event_type = 'nudge_sent'.
      cbm_id is read from EngagementEvent.trigger_id on that row.
      No DeliveryLog lookup; no DeliveryLog.thread_id migration required.

    Failure mode (directive §5.1): if no matching outbound EngagementEvent is found,
    or if the matched row carries a null trigger_id, match() returns None and logs a
    warning.  It does NOT fall back to time-proximity automatically.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def match(
        self,
        *,
        thread_id: str,
        user_id: int,
        engagement_event_id: int,
        response_channel: str,
    ) -> Optional[MatchResult]:
        """Return a MatchResult when an outbound EngagementEvent matches thread_id + user_id.

        Idempotency is the caller's responsibility: check for an existing
        StudentResponse row keyed on engagement_event_id before calling this
        method (directive §8).

        Args:
            thread_id:           Thread identifier from the inbound message.
            user_id:             Student user ID from the inbound EngagementEvent.
            engagement_event_id: PK of the inbound EngagementEvent row.
            response_channel:    Channel on which the student reply arrived.

        Returns:
            MatchResult with confidence=1.0 and match_method="thread_id" on success.
            None when thread_id is empty, no outbound EngagementEvent is found, or
            the matched event has a null trigger_id (all cases log a warning).
        """
        if not thread_id:
            logger.debug(
                "ThreadIdMatcher: thread_id is empty — skipping match for user_id=%s.",
                user_id,
            )
            return None

        outbound_event: Optional[EngagementEvent] = (
            self._session.query(EngagementEvent)
            .filter(
                EngagementEvent.thread_id  == thread_id,
                EngagementEvent.user_id    == user_id,
                EngagementEvent.event_type == "nudge_sent",
            )
            .order_by(EngagementEvent.created_at.desc())
            .first()
        )

        if outbound_event is None:
            logger.warning(
                "ThreadIdMatcher: no outbound nudge_sent EngagementEvent found for "
                "thread_id=%r user_id=%s — no association created.",
                thread_id, user_id,
            )
            return None

        if outbound_event.trigger_id is None:
            logger.warning(
                "ThreadIdMatcher: outbound EngagementEvent id=%s has null trigger_id "
                "for thread_id=%r user_id=%s — no association created.",
                outbound_event.id, thread_id, user_id,
            )
            return None

        return MatchResult(
            cbm_id              = outbound_event.trigger_id,
            engagement_event_id = engagement_event_id,
            user_id             = user_id,
            response_channel    = response_channel,
            match_method        = MATCH_METHOD_THREAD_ID,
            confidence          = CONFIDENCE_DETERMINISTIC,
            matched_at          = datetime.utcnow(),
        )


# ---------------------------------------------------------------------------
# TimeProximityMatcher
# ---------------------------------------------------------------------------

class TimeProximityMatcher:
    """Heuristic response matcher using trigger CompletedDate proximity.

    Searches AI_ChatBot_TriggeredUsers for completed trigger(s) for the student
    within window_hours before the inbound message timestamp.  Applies the
    confidence formula from directive §5.2 and enforces the 0.7 ceiling.

    Ambiguity rule (directive §5.2): if two or more qualifying triggers in the
    window both reach or exceed confidence_threshold, no row is created — the
    ambiguity is unresolvable without additional signal.

    IMPORTANT (directive §9): must run in a background process or scheduled
    job only — never in the inbound request/response cycle.
    """

    def __init__(
        self,
        session: Session,
        *,
        window_hours: float = DEFAULT_WINDOW_HOURS,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._session              = session
        self._window_hours         = window_hours
        self._confidence_threshold = confidence_threshold

    def match(
        self,
        *,
        inbound_timestamp: datetime,
        user_id: int,
        engagement_event_id: int,
        response_channel: str,
    ) -> Optional[MatchResult]:
        """Return a MatchResult when exactly one unambiguous trigger is found in the window.

        Confidence formula (directive §5.2):
            hours_elapsed    = (inbound_timestamp - trigger.CompletedDate).total_seconds() / 3600
            raw_confidence   = max(0.0, 1.0 - (hours_elapsed / window_hours))
            final_confidence = raw_confidence * (1.0 / qualifying_trigger_count)
            capped at CONFIDENCE_TIME_PROXIMITY_MAX (0.7)

        Returns None when:
          - zero triggers are found in the window, or
          - the single qualifying trigger falls below confidence_threshold, or
          - two or more triggers both reach or exceed confidence_threshold (ambiguous).

        Idempotency is the caller's responsibility: check for an existing
        StudentResponse row keyed on engagement_event_id before calling this
        method (directive §8).

        Args:
            inbound_timestamp:   UTC timestamp of the inbound student message.
            user_id:             Student user ID from the inbound EngagementEvent.
            engagement_event_id: PK of the inbound EngagementEvent row.
            response_channel:    Channel on which the student reply arrived.

        Returns:
            MatchResult with confidence ≤ 0.7 and match_method="time_proximity".
            None if no unambiguous match is found.
        """
        if not inbound_timestamp:
            logger.debug(
                "TimeProximityMatcher: inbound_timestamp missing — skipping for user_id=%s.",
                user_id,
            )
            return None

        window_start = inbound_timestamp - timedelta(hours=self._window_hours)

        candidates: list[TriggeredUser] = (
            self._session.query(TriggeredUser)
            .filter(
                TriggeredUser.UserID        == user_id,
                TriggeredUser.Completed     == 1,
                TriggeredUser.CompletedDate >= window_start,
                TriggeredUser.CompletedDate <= inbound_timestamp,
            )
            .all()
        )

        if not candidates:
            logger.debug(
                "TimeProximityMatcher: no completed triggers in window for user_id=%s.",
                user_id,
            )
            return None

        count = len(candidates)

        def _score(trigger: TriggeredUser) -> float:
            hours_elapsed = (
                inbound_timestamp - trigger.CompletedDate
            ).total_seconds() / 3600
            raw = max(0.0, 1.0 - (hours_elapsed / self._window_hours))
            return min(raw * (1.0 / count), CONFIDENCE_TIME_PROXIMITY_MAX)

        scored = [(trigger, _score(trigger)) for trigger in candidates]
        above = [(trigger, conf) for trigger, conf in scored
                 if conf >= self._confidence_threshold]

        if not above:
            logger.debug(
                "TimeProximityMatcher: best confidence below threshold %.2f "
                "for user_id=%s — no match.",
                self._confidence_threshold, user_id,
            )
            return None

        if len(above) > 1:
            logger.warning(
                "TimeProximityMatcher: %d triggers at or above threshold %.2f "
                "for user_id=%s — ambiguous, no association created.",
                len(above), self._confidence_threshold, user_id,
            )
            return None

        best_trigger, best_confidence = above[0]

        return MatchResult(
            cbm_id              = best_trigger.CBM_ID,
            engagement_event_id = engagement_event_id,
            user_id             = user_id,
            response_channel    = response_channel,
            match_method        = MATCH_METHOD_TIME_PROXIMITY,
            confidence          = best_confidence,
            matched_at          = datetime.utcnow(),
        )
