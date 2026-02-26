"""Unit tests for TriggerProcessingService.process() in isolation."""

from services.trigger_processing_service import TriggerProcessingService

service = TriggerProcessingService()

BASE_PAYLOAD = {
    "student_id": "S1",
    "timestamp": "2026-02-10T00:00:00Z",
    "metadata": {},
}


def test_nudge_needed_plans_nudge_action():
    result = service.process({**BASE_PAYLOAD, "trigger_type": "nudge_needed", "event_id": "E1"})
    assert result["event_id"] == "E1"
    assert result["accepted"] is True
    assert result["actions_planned"] == ["queue_nudge_message"]
    assert "notes" in result


def test_progress_milestone_plans_congrats_action():
    result = service.process({**BASE_PAYLOAD, "trigger_type": "progress_milestone", "event_id": "E2"})
    assert result["accepted"] is True
    assert result["actions_planned"] == ["queue_congrats_message"]
    assert "notes" in result


def test_unknown_trigger_type_is_rejected():
    result = service.process({**BASE_PAYLOAD, "trigger_type": "something_else", "event_id": "E3"})
    assert result["accepted"] is False
    assert result["actions_planned"] == []
    assert "notes" in result
