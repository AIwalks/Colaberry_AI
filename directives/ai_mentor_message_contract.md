# Directive: AI Mentor Message Contract

## 1. Purpose

This endpoint receives inbound messages from students across any supported channel (WhatsApp, SMS, email, voice, web). It acts as the single entry point for the Colaberry AI mentoring system.

The endpoint validates the request, looks up the student's lifecycle status from `AI_ChatBot_TriggerData`, echoes back a deterministic acknowledgement, and writes to both `AI_ChatBot_AuditLog` and `AI_ChatBot_EngagementEvents`. Outbound delivery via `OutboundDeliveryService` is wired into the trigger worker path (not the inbound message path directly).

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

These values are fixed — no AI generation:

| Field | Fixed Value |
|---|---|
| `student_status.lifecycle_stage` | Real value from `AI_ChatBot_TriggerData.ActiveStatus` — falls back to `"unknown"` if student not found |
| `student_status.summary` | Real value from `AI_ChatBot_TriggerData.StatusII` — falls back to `"Student not found."` if not found |
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

These are **out of scope** for the inbound message path:

- No AI-generated response text
- No real-time outbound delivery on the inbound path — outbound is handled by the trigger worker via `OutboundDeliveryService`

---

## 6a. Runtime Behaviour Now Active

The following are live at runtime when `MSSQL_DATABASE_URL` is set:

- **Student lookup:** `DbStudentStatusFetcher` reads `AI_ChatBot_TriggerData` by `UserID`; returns `lifecycle_stage` and `summary`
- **Audit log:** `AuditLogService` writes to `AI_ChatBot_AuditLog` on every inbound request (`entry_type="incoming_message"`)
- **Engagement event:** `EngagementTrackerService` writes to `AI_ChatBot_EngagementEvents` on every inbound request (`event_type="incoming_message"`)
- **Outbound delivery (trigger path):** `OutboundDeliveryService.send_text()` is called by `MentorMessageService.process_trigger()` after a trigger row is processed; stamps `CompletedDate = datetime.utcnow()` and `Completed = 1` on the `TriggeredUser` row

### Outbound delivery env vars

| Env var | Purpose | Required |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | Twilio account identifier | No — if absent, delivery is skipped silently |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | No — if absent, delivery is skipped silently |
| `TWILIO_FROM_NUMBER` | Sending phone number (SMS) | No — if absent, delivery is skipped silently |
| `OUTBOUND_USE_WHATSAPP` | Set to `"1"` to send via WhatsApp sandbox | No — defaults to SMS |
| `OUTBOUND_TEST_PHONE` | Override destination phone for all sends | No — uses student's real `PhoneNumber` from DB if absent |

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

- [x] This directive exists at `directives/ai_mentor_message_contract.md` and is clear to a junior developer
- [x] Endpoint implementation exists in `app/` (thin route) with models validated by Pydantic
- [x] All 7 test cases from Section 7 pass locally via `pytest tests/unit/`
- [x] No secrets introduced in the repository
- [x] Layer boundaries respected: route handler is thin; business logic in `services/`
- [x] Student lookup, audit log, and engagement event writes are live and tested
- [x] Outbound delivery wired into trigger worker path with unit tests
- [x] `CompletedDate` stamped on trigger completion, verified by test
