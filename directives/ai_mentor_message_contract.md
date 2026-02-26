# Directive: AI Mentor Message Contract

## 1. Purpose

This endpoint receives inbound messages from students across any supported channel (WhatsApp, SMS, email, voice, web). It acts as the single entry point for the Colaberry AI mentoring system.

In this initial phase the endpoint validates the request, echoes back a deterministic acknowledgement, and logs the event. No AI generation, student lookup, or external delivery occurs yet.

---

## 2. Endpoint

- **Method:** `POST`
- **Path:** `/ai/mentor/message`
- **Content-Type:** `application/json`

---

## 3. Request Contract

### JSON Body

| Field | Type | Required | Rules |
|---|---|---|---|
| `student_id` | string | yes | Must be non-empty after trimming |
| `channel` | string | yes | Must be one of: `whatsapp`, `sms`, `email`, `voice`, `web` |
| `message` | string | yes | Must be non-empty after trimming |
| `timestamp` | string | no | ISO-8601 format preferred (e.g. `2025-06-15T14:30:00Z`) |
| `thread_id` | string | no | Opaque thread identifier for conversation continuity |
| `metadata` | object | no | Arbitrary key-value pairs for future use |

### Headers

| Header | Required | Behavior |
|---|---|---|
| `X-Request-Id` | no | If present and non-empty, echo the value back as `request_id` in the response. If absent or blank, the server must generate a UUID v4 and return it. |

---

## 4. Response Contract (200 OK)

The response body is `application/json` with exactly these top-level keys:

```json
{
  "request_id": "<echoed or generated UUID>",
  "received": {
    "student_id": "<from request>",
    "channel": "<from request>",
    "message": "<from request>"
  },
  "student_status": {
    "lifecycle_stage": "unknown",
    "summary": "Status lookup not yet connected"
  },
  "delivery": {
    "channel": "<from request>",
    "constraints": {
      "max_length": 1000
    }
  },
  "response_message": {
    "text": "Your message has been received and logged. A mentor will follow up shortly."
  },
  "engagement_log": {
    "logged": true,
    "event_type": "incoming_message"
  }
}
```

### Deterministic Placeholder Rules

These values are **hardcoded** for now — no external calls, no AI generation:

| Field | Fixed Value |
|---|---|
| `student_status.lifecycle_stage` | `"unknown"` |
| `student_status.summary` | `"Status lookup not yet connected"` |
| `delivery.constraints.max_length` | `1000` |
| `response_message.text` | `"Your message has been received and logged. A mentor will follow up shortly."` |
| `engagement_log.logged` | `true` |
| `engagement_log.event_type` | `"incoming_message"` |

---

## 5. Error Cases

| Status | Condition | Produced By |
|---|---|---|
| `422 Unprocessable Entity` | Required field missing, empty, or `channel` not in allowed list | FastAPI / Pydantic validation |
| `400 Bad Request` | Request body is not valid JSON | FastAPI default behavior |

No custom error handling is needed beyond what FastAPI and Pydantic provide out of the box.

---

## 6. Non-Goals (Explicit)

These are **out of scope** for this phase:

- No database reads or writes
- No external messaging (Twilio, Mandrill, voice providers)
- No real student lookup or lifecycle resolution
- No async workers or background tasks
- No AI-generated response text

Each of these will be introduced in future directives with their own contracts and tests.

---

## 7. Verification / Tests Required

All tests must live under `tests/unit/`.

### Required Test Cases

| # | Test | Expected |
|---|---|---|
| 1 | Happy path — valid request with all required fields | 200, response body matches exact structure from Section 4 |
| 2 | `X-Request-Id` header present and non-empty | `request_id` in response equals the header value |
| 3 | `X-Request-Id` header absent | `request_id` in response is a valid UUID v4 |
| 4 | `student_id` missing or empty | 422 |
| 5 | `channel` is not in the allowed list | 422 |
| 6 | `message` missing or empty | 422 |
| 7 | Optional fields omitted | 200 (no error) |

### Test Tooling

- Use `pytest` with FastAPI's `TestClient` (from `starlette.testclient`)
- Tests must be deterministic — no network calls, no database, no randomness beyond UUID generation
- UUID generation should be verifiable (check format, not exact value)

---

## 8. Definition of Done

- [ ] This directive exists at `directives/ai_mentor_message_contract.md` and is clear to a junior developer
- [ ] Endpoint implementation exists in `app/` (thin route) with models validated by Pydantic
- [ ] All 7 test cases from Section 7 pass locally via `pytest tests/unit/`
- [ ] No secrets introduced in the repository
- [ ] Layer boundaries respected: the route handler contains no business logic beyond validation and the fixed response — real logic will move to `/execution` in future phases
- [ ] No external services called during tests or at runtime
