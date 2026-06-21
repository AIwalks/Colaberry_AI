"""Unit tests for ThreadIdMatcher, TimeProximityMatcher, and persist_match.

Uses in-memory SQLite sessions — no network, no real DB required.
"""

import pytest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.models import EngagementEvent, StudentResponse, TriggeredUser
from services.student_response_matcher_service import (
    CONFIDENCE_DETERMINISTIC,
    CONFIDENCE_TIME_PROXIMITY_MAX,
    MATCH_METHOD_THREAD_ID,
    MATCH_METHOD_TIME_PROXIMITY,
    MatchResult,
    ThreadIdMatcher,
    TimeProximityMatcher,
    persist_match,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Ephemeral SQLite session — EngagementEvent table only (ThreadIdMatcher tests)."""
    engine = create_engine("sqlite:///:memory:")
    EngagementEvent.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sr_db_session():
    """Ephemeral SQLite session — StudentResponse table only (persist_match tests)."""
    engine = create_engine("sqlite:///:memory:")
    StudentResponse.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def tp_db_session():
    """Ephemeral SQLite session — TriggeredUser table only (TimeProximityMatcher tests).

    TriggeredUser has a FK reference to TriggerRules, but SQLite does not
    enforce FK constraints by default, so the referenced table need not exist.
    """
    engine = create_engine("sqlite:///:memory:")
    TriggeredUser.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nudge_event(session, *, user_id: int, thread_id: str, trigger_id):
    """Insert and return a nudge_sent EngagementEvent row."""
    evt = EngagementEvent(
        user_id    = user_id,
        event_type = "nudge_sent",
        channel    = "whatsapp",
        thread_id  = thread_id,
        trigger_id = trigger_id,
        agent_name = "OutboundDeliveryService",
        created_at = datetime.utcnow(),
    )
    session.add(evt)
    session.commit()
    session.refresh(evt)
    return evt


def _completed_trigger(session, *, user_id: int, completed_date: datetime):
    """Insert and return a completed TriggeredUser row."""
    row = TriggeredUser(
        UserID        = user_id,
        Completed     = 1,
        CompletedDate = completed_date,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _make_result(**overrides) -> MatchResult:
    """Build a MatchResult with sensible defaults; override any field via kwargs."""
    defaults = dict(
        cbm_id              = 42,
        engagement_event_id = 99,
        user_id             = 10,
        response_channel    = "whatsapp",
        match_method        = MATCH_METHOD_THREAD_ID,
        confidence          = CONFIDENCE_DETERMINISTIC,
        matched_at          = _T,
    )
    defaults.update(overrides)
    return MatchResult(**defaults)


# Fixed reference timestamp used across TimeProximityMatcher tests.
# All CompletedDate values are expressed relative to this anchor so that
# confidence arithmetic is deterministic and independent of wall-clock time.
_T = datetime(2026, 1, 15, 12, 0, 0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestThreadIdMatcher:

    def test_match_found_returns_match_result(self, db_session):
        """Outbound nudge_sent event matches → MatchResult with correct fields."""
        _nudge_event(db_session, user_id=10, thread_id="WA_THREAD_001", trigger_id=42)

        matcher = ThreadIdMatcher(db_session)
        result = matcher.match(
            thread_id           = "WA_THREAD_001",
            user_id             = 10,
            engagement_event_id = 99,
            response_channel    = "whatsapp",
        )

        assert result is not None
        assert isinstance(result, MatchResult)
        assert result.cbm_id              == 42
        assert result.engagement_event_id == 99
        assert result.user_id             == 10
        assert result.response_channel    == "whatsapp"
        assert result.match_method        == MATCH_METHOD_THREAD_ID
        assert result.confidence          == CONFIDENCE_DETERMINISTIC
        assert result.matched_at          is not None

    def test_empty_thread_id_returns_none(self, db_session):
        """Empty thread_id → None without querying the DB."""
        matcher = ThreadIdMatcher(db_session)
        result = matcher.match(
            thread_id           = "",
            user_id             = 10,
            engagement_event_id = 99,
            response_channel    = "whatsapp",
        )
        assert result is None

    def test_no_matching_outbound_event_returns_none(self, db_session):
        """No nudge_sent row matches the thread_id → None."""
        matcher = ThreadIdMatcher(db_session)
        result = matcher.match(
            thread_id           = "NONEXISTENT_THREAD",
            user_id             = 10,
            engagement_event_id = 99,
            response_channel    = "whatsapp",
        )
        assert result is None

    def test_matching_event_with_null_trigger_id_returns_none(self, db_session):
        """Outbound event found but trigger_id is None → None (unlinked event)."""
        _nudge_event(db_session, user_id=10, thread_id="WA_THREAD_NOTRIG", trigger_id=None)

        matcher = ThreadIdMatcher(db_session)
        result = matcher.match(
            thread_id           = "WA_THREAD_NOTRIG",
            user_id             = 10,
            engagement_event_id = 99,
            response_channel    = "whatsapp",
        )
        assert result is None


# ---------------------------------------------------------------------------
# TimeProximityMatcher
# ---------------------------------------------------------------------------

# Shared matcher config used across all TimeProximityMatcher tests.
_WINDOW_HOURS = 72.0
_THRESHOLD    = 0.3


class TestTimeProximityMatcher:

    def test_one_trigger_in_window_returns_match_result(self, tp_db_session):
        """Single completed trigger 1 h ago → MatchResult, confidence capped at 0.7.

        Confidence arithmetic (count=1, hours_elapsed=1, window=72):
            raw   = 1 - (1 / 72) = 0.9861
            final = 0.9861 * (1/1) = 0.9861  →  capped at 0.7
        """
        trigger = _completed_trigger(
            tp_db_session,
            user_id        = 10,
            completed_date = _T - timedelta(hours=1),
        )

        matcher = TimeProximityMatcher(
            tp_db_session,
            window_hours         = _WINDOW_HOURS,
            confidence_threshold = _THRESHOLD,
        )
        result = matcher.match(
            inbound_timestamp   = _T,
            user_id             = 10,
            engagement_event_id = 99,
            response_channel    = "sms",
        )

        assert result is not None
        assert isinstance(result, MatchResult)
        assert result.cbm_id              == trigger.CBM_ID
        assert result.engagement_event_id == 99
        assert result.user_id             == 10
        assert result.response_channel    == "sms"
        assert result.match_method        == MATCH_METHOD_TIME_PROXIMITY
        assert result.confidence          <= CONFIDENCE_TIME_PROXIMITY_MAX
        assert result.confidence          == CONFIDENCE_TIME_PROXIMITY_MAX  # capped at 0.7
        assert result.matched_at          is not None

    def test_no_candidates_returns_none(self, tp_db_session):
        """Empty DB → None."""
        matcher = TimeProximityMatcher(
            tp_db_session,
            window_hours         = _WINDOW_HOURS,
            confidence_threshold = _THRESHOLD,
        )
        result = matcher.match(
            inbound_timestamp   = _T,
            user_id             = 10,
            engagement_event_id = 99,
            response_channel    = "sms",
        )
        assert result is None

    def test_confidence_below_threshold_returns_none(self, tp_db_session):
        """Trigger 60 h ago → confidence 0.167 < threshold 0.3 → None.

        Confidence arithmetic (count=1, hours_elapsed=60, window=72):
            raw   = 1 - (60 / 72) = 0.1667
            final = 0.1667 * (1/1) = 0.1667  <  threshold 0.3
        """
        _completed_trigger(
            tp_db_session,
            user_id        = 10,
            completed_date = _T - timedelta(hours=60),
        )

        matcher = TimeProximityMatcher(
            tp_db_session,
            window_hours         = _WINDOW_HOURS,
            confidence_threshold = _THRESHOLD,
        )
        result = matcher.match(
            inbound_timestamp   = _T,
            user_id             = 10,
            engagement_event_id = 99,
            response_channel    = "sms",
        )
        assert result is None

    def test_two_candidates_both_above_threshold_returns_none(self, tp_db_session):
        """Two recent triggers, both above threshold after count-division → ambiguous → None.

        Confidence arithmetic (count=2, window=72):
            trigger_A (1 h ago):  raw=0.9861, final=0.9861*(1/2)=0.4930  ≥ 0.3
            trigger_B (2 h ago):  raw=0.9722, final=0.9722*(1/2)=0.4861  ≥ 0.3
        Two above threshold → ambiguous.
        """
        _completed_trigger(tp_db_session, user_id=10, completed_date=_T - timedelta(hours=1))
        _completed_trigger(tp_db_session, user_id=10, completed_date=_T - timedelta(hours=2))

        matcher = TimeProximityMatcher(
            tp_db_session,
            window_hours         = _WINDOW_HOURS,
            confidence_threshold = _THRESHOLD,
        )
        result = matcher.match(
            inbound_timestamp   = _T,
            user_id             = 10,
            engagement_event_id = 99,
            response_channel    = "sms",
        )
        assert result is None

    def test_trigger_outside_window_is_ignored(self, tp_db_session):
        """Trigger 73 h ago (outside 72 h window) → no candidates → None."""
        _completed_trigger(
            tp_db_session,
            user_id        = 10,
            completed_date = _T - timedelta(hours=73),
        )

        matcher = TimeProximityMatcher(
            tp_db_session,
            window_hours         = _WINDOW_HOURS,
            confidence_threshold = _THRESHOLD,
        )
        result = matcher.match(
            inbound_timestamp   = _T,
            user_id             = 10,
            engagement_event_id = 99,
            response_channel    = "sms",
        )
        assert result is None


# ---------------------------------------------------------------------------
# persist_match
# ---------------------------------------------------------------------------

class TestPersistMatch:

    def test_inserts_student_response_from_match_result(self, sr_db_session):
        """persist_match inserts a StudentResponse whose fields mirror the MatchResult."""
        result = _make_result()

        row = persist_match(sr_db_session, result)

        assert row is not None
        assert isinstance(row, StudentResponse)
        assert row.id                  is not None
        assert row.cbm_id              == result.cbm_id
        assert row.engagement_event_id == result.engagement_event_id
        assert row.user_id             == result.user_id
        assert row.response_channel    == result.response_channel
        assert row.match_method        == result.match_method
        assert row.confidence          == result.confidence
        assert row.matched_at          == result.matched_at

        # Verify the row actually exists in the DB.
        db_row = (
            sr_db_session.query(StudentResponse)
            .filter_by(engagement_event_id=result.engagement_event_id)
            .one()
        )
        assert db_row.id == row.id

    def test_duplicate_same_cbm_id_returns_existing_no_second_insert(self, sr_db_session):
        """Second call with same engagement_event_id + cbm_id returns existing row.

        The DB must contain exactly one row for the engagement_event_id after
        both calls (directive §8 — duplicate insert is a no-op).
        """
        result = _make_result()

        first  = persist_match(sr_db_session, result)
        second = persist_match(sr_db_session, result)

        assert first  is not None
        assert second is not None
        assert second.id == first.id  # same row, not a new one

        count = (
            sr_db_session.query(StudentResponse)
            .filter_by(engagement_event_id=result.engagement_event_id)
            .count()
        )
        assert count == 1

    def test_conflict_different_cbm_id_returns_none_no_insert(self, sr_db_session):
        """Second call with same engagement_event_id but different cbm_id returns None.

        The DB must still contain exactly one row — the original — after both
        calls (directive §8 — conflict is blocked, not overwritten).
        """
        first_result  = _make_result(cbm_id=42)
        second_result = _make_result(cbm_id=99)  # different cbm_id, same event id

        first    = persist_match(sr_db_session, first_result)
        conflict = persist_match(sr_db_session, second_result)

        assert first    is not None
        assert conflict is None

        rows = (
            sr_db_session.query(StudentResponse)
            .filter_by(engagement_event_id=first_result.engagement_event_id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].cbm_id == 42  # original row untouched
