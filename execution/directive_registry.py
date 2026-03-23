"""Directive registry — wires directive names to handler functions.

One responsibility: build and return a configured DirectiveRunner.

No DB, no HTTP, no worker code. Pure imports and registration only.

Usage
-----
    from execution.directive_registry import build_registry

    runner = build_registry()
    result = runner.run("trigger_processing", {"event_id": "E1", "trigger_type": "InClass", "student_id": "42"})
"""

from execution.directive_runner import DirectiveRunner
from services.trigger_processing_service import TriggerProcessingService


def _handle_trigger_processing(payload: dict) -> dict:
    """Delegate to TriggerProcessingService (pure, no DB)."""
    return TriggerProcessingService().process(payload)


def build_registry() -> DirectiveRunner:
    """Create and return a DirectiveRunner with all directives registered.

    Returns
    -------
    DirectiveRunner
        Fully configured runner ready to dispatch directives.
    """
    runner = DirectiveRunner()
    runner.register("trigger_processing", _handle_trigger_processing)
    return runner
