"""Unit tests for execution/directive_registry.py — pure logic, no I/O."""

from unittest.mock import MagicMock, patch

from execution.directive_registry import build_registry
from execution.directive_runner import DirectiveRunner


# ---------------------------------------------------------------------------
# build_registry returns a DirectiveRunner
# ---------------------------------------------------------------------------

def test_build_registry_returns_directive_runner():
    runner = build_registry()
    assert isinstance(runner, DirectiveRunner)


def test_build_registry_returns_new_instance_each_call():
    runner_a = build_registry()
    runner_b = build_registry()
    assert runner_a is not runner_b


# ---------------------------------------------------------------------------
# "trigger_processing" is registered
# ---------------------------------------------------------------------------

def test_trigger_processing_is_registered():
    runner = build_registry()
    assert "trigger_processing" in runner.registered_directives


def test_registered_directives_contains_only_expected_names():
    runner = build_registry()
    assert runner.registered_directives == ["trigger_processing"]


# ---------------------------------------------------------------------------
# running "trigger_processing" calls the handler
# ---------------------------------------------------------------------------

def test_run_trigger_processing_calls_service_process():
    payload = {"event_id": "E1", "trigger_type": "nudge_needed", "student_id": "42"}
    fake_result = {"event_id": "E1", "accepted": True, "actions_planned": [], "notes": ""}

    with patch(
        "execution.directive_registry.TriggerProcessingService"
    ) as MockService:
        mock_instance = MagicMock()
        mock_instance.process.return_value = fake_result
        MockService.return_value = mock_instance

        runner = build_registry()
        result = runner.run("trigger_processing", payload)

    mock_instance.process.assert_called_once_with(payload)
    assert result == fake_result


def test_run_trigger_processing_passes_payload_unchanged():
    payload = {"event_id": "E2", "trigger_type": "InClass", "student_id": "99"}

    with patch(
        "execution.directive_registry.TriggerProcessingService"
    ) as MockService:
        mock_instance = MagicMock()
        mock_instance.process.return_value = {}
        MockService.return_value = mock_instance

        runner = build_registry()
        runner.run("trigger_processing", payload)

    mock_instance.process.assert_called_once_with(payload)


def test_run_trigger_processing_returns_handler_result():
    expected = {"event_id": "E3", "accepted": False, "actions_planned": [], "notes": "test"}

    with patch(
        "execution.directive_registry.TriggerProcessingService"
    ) as MockService:
        mock_instance = MagicMock()
        mock_instance.process.return_value = expected
        MockService.return_value = mock_instance

        runner = build_registry()
        result = runner.run("trigger_processing", {})

    assert result == expected


# ---------------------------------------------------------------------------
# Registry does not modify global state
# ---------------------------------------------------------------------------

def test_registering_on_one_runner_does_not_affect_another():
    runner_a = build_registry()
    runner_b = build_registry()

    runner_a.register("extra_directive", lambda p: "extra")

    assert "extra_directive" in runner_a.registered_directives
    assert "extra_directive" not in runner_b.registered_directives


def test_build_registry_called_twice_produces_independent_runners():
    runner_a = build_registry()
    runner_b = build_registry()

    runner_a.register("only_in_a", lambda p: None)

    assert runner_a.registered_directives != runner_b.registered_directives


def test_build_registry_does_not_mutate_shared_state():
    """Calling build_registry multiple times always produces the same base set."""
    for _ in range(3):
        runner = build_registry()
        assert runner.registered_directives == ["trigger_processing"]
