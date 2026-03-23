"""Unit tests for DirectiveRunner — pure logic, no I/O."""

import pytest

from execution.directive_runner import DirectiveNotFoundError, DirectiveRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def handler_echo(payload: dict) -> dict:
    """Returns the payload unchanged."""
    return payload


def handler_double(payload: dict) -> int:
    """Returns payload['value'] * 2."""
    return payload["value"] * 2


# ---------------------------------------------------------------------------
# run — happy path
# ---------------------------------------------------------------------------

def test_run_calls_registered_handler_and_returns_result():
    runner = DirectiveRunner({"echo": handler_echo})
    result = runner.run("echo", {"msg": "hello"})
    assert result == {"msg": "hello"}


def test_run_passes_payload_to_handler():
    runner = DirectiveRunner({"double": handler_double})
    result = runner.run("double", {"value": 5})
    assert result == 10


def test_run_with_empty_payload():
    runner = DirectiveRunner({"echo": handler_echo})
    result = runner.run("echo", {})
    assert result == {}


# ---------------------------------------------------------------------------
# run — DirectiveNotFoundError
# ---------------------------------------------------------------------------

def test_run_raises_directive_not_found_for_unknown_name():
    runner = DirectiveRunner({"echo": handler_echo})
    with pytest.raises(DirectiveNotFoundError):
        runner.run("nonexistent", {})


def test_run_raises_directive_not_found_with_name_in_message():
    runner = DirectiveRunner({})
    with pytest.raises(DirectiveNotFoundError, match="unknown_directive"):
        runner.run("unknown_directive", {})


def test_run_raises_directive_not_found_on_empty_registry():
    runner = DirectiveRunner()
    with pytest.raises(DirectiveNotFoundError):
        runner.run("anything", {})


# ---------------------------------------------------------------------------
# registered_directives
# ---------------------------------------------------------------------------

def test_registered_directives_returns_sorted_names():
    runner = DirectiveRunner({"zebra": handler_echo, "apple": handler_echo, "mango": handler_echo})
    assert runner.registered_directives == ["apple", "mango", "zebra"]


def test_registered_directives_returns_empty_list_when_no_handlers():
    runner = DirectiveRunner()
    assert runner.registered_directives == []


def test_registered_directives_returns_single_name():
    runner = DirectiveRunner({"only_one": handler_echo})
    assert runner.registered_directives == ["only_one"]


# ---------------------------------------------------------------------------
# register — adds handler at runtime
# ---------------------------------------------------------------------------

def test_register_adds_handler_and_run_succeeds():
    runner = DirectiveRunner()
    runner.register("new_directive", handler_echo)
    result = runner.run("new_directive", {"key": "value"})
    assert result == {"key": "value"}


def test_register_appears_in_registered_directives():
    runner = DirectiveRunner()
    runner.register("added", handler_echo)
    assert "added" in runner.registered_directives


def test_register_overwrites_existing_handler():
    runner = DirectiveRunner({"greet": lambda p: "hello"})
    runner.register("greet", lambda p: "goodbye")
    assert runner.run("greet", {}) == "goodbye"


def test_register_multiple_handlers_all_callable():
    runner = DirectiveRunner()
    runner.register("a", handler_echo)
    runner.register("b", handler_double)
    assert runner.run("a", {"x": 1}) == {"x": 1}
    assert runner.run("b", {"value": 3}) == 6
