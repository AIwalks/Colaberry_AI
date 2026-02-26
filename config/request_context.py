"""Request-scoped context variable for propagating request_id."""

import contextvars

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def set_request_id(value: str) -> None:
    request_id_var.set(value)


def get_request_id() -> str:
    return request_id_var.get()


def clear_request_id() -> None:
    request_id_var.set("-")
