"""Directive runner — routes a directive name to a registered callable.

One responsibility: look up a directive by name and call it with a payload.

No I/O, no database, no HTTP. Pure routing logic only.

Usage
-----
    registry = {
        "send_nudge": handle_nudge,
        "log_event":  handle_log,
    }
    runner = DirectiveRunner(registry)
    result = runner.run("send_nudge", {"user_id": 1, "message": "Hello"})
"""

from __future__ import annotations

from typing import Any, Callable


class DirectiveNotFoundError(Exception):
    """Raised when a directive name has no registered handler."""


class DirectiveRunner:
    """Routes a directive name to its registered handler function.

    Parameters
    ----------
    registry : dict[str, Callable[[dict], Any]]
        Mapping of directive name to a callable that accepts a payload dict
        and returns a result. Defaults to an empty registry.
    """

    def __init__(self, registry: dict[str, Callable[[dict], Any]] | None = None) -> None:
        self._registry: dict[str, Callable[[dict], Any]] = registry or {}

    def register(self, directive_name: str, handler: Callable[[dict], Any]) -> None:
        """Register a handler for a directive name.

        Parameters
        ----------
        directive_name : str
            The name of the directive to register.
        handler : Callable[[dict], Any]
            The function to call when this directive is run.
        """
        self._registry[directive_name] = handler

    def run(self, directive_name: str, payload: dict) -> Any:
        """Run a directive by name with the given payload.

        Parameters
        ----------
        directive_name : str
            The name of the directive to execute.
        payload : dict
            Arbitrary data passed to the handler.

        Returns
        -------
        Any
            The return value of the registered handler.

        Raises
        ------
        DirectiveNotFoundError
            If no handler is registered for the given directive name.
        """
        handler = self._registry.get(directive_name)
        if handler is None:
            raise DirectiveNotFoundError(
                f"No handler registered for directive: {directive_name!r}"
            )
        return handler(payload)

    @property
    def registered_directives(self) -> list[str]:
        """Return a sorted list of all registered directive names."""
        return sorted(self._registry.keys())
