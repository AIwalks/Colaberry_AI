"""Background response-matching worker.

Scans AI_ChatBot_EngagementEvents for inbound student messages that have
not yet been associated with a trigger record, then attempts to link each
one to a TriggeredUser row via the two matching strategies defined in
directives/student_response_tracking_contract.md.

Run directly:
    python -m services.worker.response_matching_worker

Or import and call from a scheduler or management script:
    from services.worker.response_matching_worker import run_response_matching
    summary = run_response_matching()

CRITICAL (directive §9): this worker must NEVER be called from within the
inbound request/response cycle. It runs as a background process or scheduled
job only — never as part of a FastAPI route handler or any construct that
shares the HTTP request lifetime.
"""

import logging
from datetime import datetime

from config.database import MSSQL_CONFIGURED, SessionLocal
from services.models import EngagementEvent, StudentResponse
from services.student_response_matcher_service import (
    ThreadIdMatcher,
    TimeProximityMatcher,
    persist_match,
)

logger = logging.getLogger(__name__)

# event_type value that marks an inbound student message in AI_ChatBot_EngagementEvents.
# Must match the value written by MentorMessageService → EngagementTrackerService.log_event().
_INBOUND_EVENT_TYPE = "incoming_message"


def run_response_matching(
    *,
    window_hours: float = 72.0,
    confidence_threshold: float = 0.3,
    batch_size: int = 100,
) -> dict:
    """Attempt to match unmatched inbound EngagementEvent rows to TriggeredUser records.

    For each unmatched inbound event the worker tries, in order:
      1. ThreadIdMatcher  — deterministic; requires event.thread_id to be present.
      2. TimeProximityMatcher — heuristic; runs when thread match returns None.

    A StudentResponse row is inserted via persist_match() only when a matcher
    returns a MatchResult.  Idempotency is enforced by persist_match():
    duplicate calls for the same engagement_event_id are safe no-ops.

    Known limitation: MentorMessageService.handle() currently writes inbound
    EngagementEvent rows with user_id=None.  Events without a user_id cannot be
    matched and are skipped.  This gap must be resolved in MentorMessageService
    before full matching coverage is possible.

    Args:
        window_hours:         Lookback window (hours) for TimeProximityMatcher.
        confidence_threshold: Minimum confidence for TimeProximityMatcher to record
                              a match.  Events where no candidate clears this
                              threshold produce no StudentResponse row.
        batch_size:           Maximum number of inbound events to examine per call.
                              Use repeated calls or a scheduler to drain a larger
                              backlog.

    Returns:
        Summary dict:
          processed  — number of inbound events examined.
          matched    — StudentResponse rows inserted (or confirmed existing).
          no_match   — events where both matchers returned None.
          conflicts  — events where an existing StudentResponse had a different
                       cbm_id; insert was blocked (manual override required).
          skipped    — events skipped because user_id is None.
    """
    if not MSSQL_CONFIGURED:
        logger.info("run_response_matching: MSSQL not configured — skipping.")
        return {
            "processed": 0,
            "matched":   0,
            "no_match":  0,
            "conflicts": 0,
            "skipped":   0,
        }

    summary = {
        "processed": 0,
        "matched":   0,
        "no_match":  0,
        "conflicts": 0,
        "skipped":   0,
    }

    with SessionLocal() as session:
        # Subquery: engagement_event_ids that already have a StudentResponse row.
        already_matched = session.query(StudentResponse.engagement_event_id)

        unmatched: list[EngagementEvent] = (
            session.query(EngagementEvent)
            .filter(
                EngagementEvent.event_type == _INBOUND_EVENT_TYPE,
                EngagementEvent.id.notin_(already_matched),
            )
            .order_by(EngagementEvent.id)
            .limit(batch_size)
            .all()
        )

        if not unmatched:
            logger.debug("run_response_matching: no unmatched inbound events found.")
            return summary

        thread_matcher = ThreadIdMatcher(session)
        time_matcher   = TimeProximityMatcher(
            session,
            window_hours         = window_hours,
            confidence_threshold = confidence_threshold,
        )

        for event in unmatched:
            summary["processed"] += 1

            if event.user_id is None:
                logger.debug(
                    "run_response_matching: event id=%s has user_id=None — skipped. "
                    "MentorMessageService must be updated to pass student_id as user_id.",
                    event.id,
                )
                summary["skipped"] += 1
                continue

            match_result = None

            # Step 1 — thread-based match (deterministic, confidence=1.0).
            # Only attempted when the event carries a thread identifier.
            if event.thread_id:
                match_result = thread_matcher.match(
                    thread_id           = event.thread_id,
                    user_id             = event.user_id,
                    engagement_event_id = event.id,
                    response_channel    = event.channel or "",
                )

            # Step 2 — time-proximity match (heuristic, confidence ≤ 0.7).
            # Only attempted when thread match was not possible or returned None.
            if match_result is None:
                inbound_ts = event.created_at or datetime.utcnow()
                match_result = time_matcher.match(
                    inbound_timestamp   = inbound_ts,
                    user_id             = event.user_id,
                    engagement_event_id = event.id,
                    response_channel    = event.channel or "",
                )

            if match_result is None:
                summary["no_match"] += 1
                continue

            persisted = persist_match(session, match_result)

            if persisted is None:
                summary["conflicts"] += 1
            else:
                summary["matched"] += 1

    logger.info("run_response_matching complete: %s", summary)
    return summary


if __name__ == "__main__":
    result = run_response_matching()
    print(
        f"Response matching complete — "
        f"processed={result['processed']} "
        f"matched={result['matched']} "
        f"no_match={result['no_match']} "
        f"conflicts={result['conflicts']} "
        f"skipped={result['skipped']}"
    )
