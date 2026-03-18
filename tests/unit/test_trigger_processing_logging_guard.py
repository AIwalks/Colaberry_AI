"""Verify DbTriggerProcessingService.process() does not fail
when event_id is a non-numeric string.

Regression guard for the safe_trigger_id normalization:
  "EVT-001".isdigit() is False → safe_trigger_id must be None.
The EngagementTrackerService call is wrapped in try/except, so any
logging failure must never surface to the caller.

No real DB required. No ORM model classes are mocked.
A duck-typed SimpleNamespace stands in for the rule row.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_process_non_numeric_event_id_does_not_fail():
    """process() must return accepted=True when event_id is a non-numeric string."""
    from services.trigger_processing_service import DbTriggerProcessingService

    # Duck-typed fake rule — not a mock of the ORM class
    fake_rule = SimpleNamespace(
        CB_ID        = 1,
        TriggerType  = "nudge_needed",
        KPI          = None,
        Severity     = 1,
        TriggerLow   = None,
        TriggerHigh  = None,
        AgentID      = None,
    )

    # Mock session that returns the fake rule and supports the context manager
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalars.return_value.first.return_value = fake_rule
    mock_session.get.return_value = None  # student not found — handled gracefully

    payload = {
        "trigger_type": "nudge_needed",
        "student_id":   "1",
        "event_id":     "EVT-001",   # non-numeric — the key test case
        "timestamp":    "2026-03-13T00:00:00Z",
    }

    # Patch SessionLocal at source so the local import inside process() sees the mock
    with patch("config.database.SessionLocal", MagicMock(return_value=mock_session)):
        result = DbTriggerProcessingService().process(payload)

    assert result["accepted"] is True
    assert result["event_id"] == "EVT-001"
