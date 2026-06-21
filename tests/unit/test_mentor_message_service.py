"""Unit tests for MentorMessageService.handle() in isolation."""

from unittest.mock import patch

from services.engagement_tracker_service import EngagementTrackerService
from services.mentor_message_service import MentorMessageService


class FakeBody:
    student_id = "A100"
    channel = "web"
    message = "Hello"


class FakeStatusFetcher:
    def fetch_status(self, student_id: str) -> dict[str, str]:
        return {"lifecycle_stage": "active", "summary": "Service test override"}


def test_handle_returns_correct_shape_and_values():
    result = MentorMessageService().handle(
        body=FakeBody(), request_id="req-1", status_fetcher=FakeStatusFetcher(),
    )

    assert result["request_id"] == "req-1"
    assert result["received"]["student_id"] == "A100"
    assert result["student_status"]["lifecycle_stage"] == "active"
    assert result["student_status"]["summary"] == "Service test override"
    assert result["delivery"]["constraints"]["max_length"] == 1000
    assert result["engagement_log"]["logged"] is True


# ---------------------------------------------------------------------------
# user_id propagation — Sprint 10 inbound gap fix
# ---------------------------------------------------------------------------

class _NumericBody:
    student_id = "42"
    channel = "web"
    message = "Hello"
    thread_id = "T-001"


class _NonNumericBody:
    student_id = "A100"
    channel = "web"
    message = "Hello"
    thread_id = None


def test_handle_passes_int_user_id_to_log_event_when_student_id_is_numeric():
    """Numeric student_id is converted to int and forwarded to EngagementTrackerService.log_event."""
    captured: dict = {}

    def _capture(**kwargs):
        captured.update(kwargs)

    with patch.object(EngagementTrackerService, "log_event", side_effect=_capture):
        MentorMessageService().handle(
            body=_NumericBody(), request_id="req-2", status_fetcher=FakeStatusFetcher()
        )

    assert captured.get("user_id") == 42
    assert captured.get("event_type") == "incoming_message"
    assert captured.get("thread_id") == "T-001"


def test_handle_passes_none_user_id_to_log_event_when_student_id_is_non_numeric():
    """Non-numeric student_id cannot be coerced; log_event receives user_id=None."""
    captured: dict = {}

    def _capture(**kwargs):
        captured.update(kwargs)

    with patch.object(EngagementTrackerService, "log_event", side_effect=_capture):
        MentorMessageService().handle(
            body=_NonNumericBody(), request_id="req-3", status_fetcher=FakeStatusFetcher()
        )

    assert captured.get("user_id") is None
    assert captured.get("event_type") == "incoming_message"
