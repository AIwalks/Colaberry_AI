"""Deterministic trigger-type mapping (no I/O, no external calls)."""

_TRIGGER_MAP = {
    "nudge_needed": {
        "accepted": True,
        "actions_planned": ["queue_nudge_message"],
        "notes": "Nudge action planned (deterministic rule).",
    },
    "progress_milestone": {
        "accepted": True,
        "actions_planned": ["queue_congrats_message"],
        "notes": "Congrats action planned (deterministic rule).",
    },
}

_UNKNOWN = {
    "accepted": False,
    "actions_planned": [],
    "notes": "Unknown trigger type. No actions planned.",
}


class TriggerProcessingService:

    def process(self, payload: dict) -> dict:
        trigger_type = payload.get("trigger_type", "")
        result = _TRIGGER_MAP.get(trigger_type, _UNKNOWN)
        return {"event_id": payload["event_id"], **result}
