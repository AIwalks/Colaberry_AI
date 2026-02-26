"""Unit tests for MentorMessageService.handle() in isolation."""

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
