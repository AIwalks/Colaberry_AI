"""Unit tests — thread_id is persisted on EngagementEvent for inbound messages.

Verifies that MentorMessageService.handle() passes the thread_id from the
inbound request body through to EngagementTrackerService.log_event().

No database. No network. EngagementTrackerService.log_event is patched to
capture the keyword arguments it was called with.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-Api-Key": "test-key"})

_BASE_BODY = {
    "student_id": "stu-001",
    "channel": "web",
    "message": "Hello",
}


def _captured_thread_id(body: dict) -> str | None:
    """POST to /ai/mentor/message with the given body.

    Patches EngagementTrackerService.log_event, makes the request, and returns
    the thread_id keyword argument that log_event was called with.
    """
    with patch(
        "services.mentor_message_service.EngagementTrackerService.log_event",
        return_value=1,
    ) as mock_log:
        resp = client.post("/ai/mentor/message", json=body)
        assert resp.status_code == 200, resp.text
        assert mock_log.called, "EngagementTrackerService.log_event was not called"
        _, kwargs = mock_log.call_args
        return kwargs.get("thread_id")


def test_thread_id_present_is_stored():
    """thread_id in request body must be forwarded to log_event."""
    body = {**_BASE_BODY, "thread_id": "thread-abc-123"}
    assert _captured_thread_id(body) == "thread-abc-123"


def test_thread_id_absent_stores_none():
    """When thread_id is omitted, log_event must receive thread_id=None."""
    assert _captured_thread_id(_BASE_BODY) is None
