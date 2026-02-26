# Directive: Trigger Processing Contract

## Purpose

This endpoint receives event triggers from upstream systems (e.g. LMS, scheduler, analytics) and decides which actions to plan in response. It is the entry point for all automated student-lifecycle events in the Colaberry AI system.

In this MVP phase the endpoint applies deterministic mapping rules — no I/O, no AI, no side effects.

---

## Trigger Input Contract (JSON)

**Method:** `POST`
**Path:** `/ai/trigger/process`
**Content-Type:** `application/json`

| Field | Type | Required | Rules |
|---|---|---|---|
| `trigger_type` | string | yes | Non-empty after trimming |
| `student_id` | string | yes | Non-empty after trimming |
| `event_id` | string | yes | Non-empty after trimming; unique per event |
| `timestamp` | string | yes | ISO-8601 format (e.g. `2025-06-15T14:30:00Z`) |
| `metadata` | object | no | Arbitrary key-value pairs for future use |

---

## Deterministic Behavior (MVP)

The service maps `trigger_type` to a planned action list using fixed rules. No database lookups, no external calls.

| `trigger_type` | `accepted` | `actions_planned` | `notes` |
|---|---|---|---|
| `"nudge_needed"` | `true` | `["queue_nudge_message"]` | `"Nudge action planned (deterministic rule)."` |
| `"progress_milestone"` | `true` | `["queue_congrats_message"]` | `"Congrats action planned (deterministic rule)."` |
| any other value | `false` | `[]` | `"Unknown trigger type. No actions planned."` |

---

## Response Contract (JSON)

**Status:** `200 OK`
**Content-Type:** `application/json`

```json
{
  "event_id": "<echoed from request>",
  "accepted": true,
  "actions_planned": ["queue_nudge_message"],
  "notes": "Nudge action planned (deterministic rule)."
}
```

Top-level keys (all required in every response):

| Field | Type | Description |
|---|---|---|
| `event_id` | string | Echoed from the request |
| `accepted` | bool | `true` if trigger_type was recognized, `false` otherwise |
| `actions_planned` | list of strings | Deterministic action identifiers (may be empty) |
| `notes` | string | Human-readable explanation of the decision |

---

## Error Cases

| Status | Condition | Produced By |
|---|---|---|
| `422 Unprocessable Entity` | Required field missing or empty | FastAPI / Pydantic validation |
| `400 Bad Request` | Request body is not valid JSON | FastAPI default behavior |

No custom error handling beyond what FastAPI and Pydantic provide.

---

## Non-Goals (Explicit)

These are out of scope for this phase:

- No database reads or writes
- No external messaging (Twilio, Mandrill, voice)
- No background jobs or async workers
- No real action execution (actions are planned, not dispatched)
- No AI-generated decisions

Each will be introduced in future directives with their own contracts and tests.

---

## Required Test Coverage

All tests must live under `tests/unit/`.

| # | Test | Expected |
|---|---|---|
| 1 | Happy path — `trigger_type: "nudge_needed"` | 200, `accepted: true`, `actions_planned: ["queue_nudge_message"]` |
| 2 | Happy path — `trigger_type: "progress_milestone"` | 200, `accepted: true`, `actions_planned: ["queue_congrats_message"]` |
| 3 | Unknown trigger type — `trigger_type: "alien_signal"` | 200, `accepted: false`, `actions_planned: []` |
| 4 | Missing `student_id` | 422 |
| 5 | Missing `trigger_type` | 422 |
| 6 | Missing `event_id` | 422 |
| 7 | Response has exact top-level keys: `event_id`, `accepted`, `actions_planned`, `notes` | Structural assertion |

**Tooling:** pytest with FastAPI TestClient. Tests must be deterministic — no network, no database.

---

## Definition of Done

- [ ] This directive exists at `directives/trigger_processing_contract.md` and is clear to a junior developer
- [ ] Endpoint implementation exists in `app/` (thin route) with Pydantic validation
- [ ] Service logic lives in `services/` (deterministic mapping, no I/O)
- [ ] All 7 test cases pass locally via `pytest tests/unit/`
- [ ] No secrets introduced in the repository
- [ ] Layer boundaries respected: API route is thin; mapping logic is in a testable service
- [ ] No external services called during tests or at runtime
