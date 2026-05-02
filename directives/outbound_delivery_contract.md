# Directive: Outbound Delivery Contract

**Last updated:** 2026-04-12
**Covers:** `services/outbound_delivery_service.py`
**Called by:** `services/mentor_message_service.py` → `process_trigger()`
**Tested by:** `tests/unit/test_outbound_delivery_service.py`

---

## 1. Purpose

`OutboundDeliveryService.send_text()` is the single outbound channel adapter for the Colaberry AI system.

**What it does:**
- Looks up a student's contact info (`PhoneNumber`, `Email`) from `AI_ChatBot_TriggerData` using `user_id`
- Attempts delivery via every configured channel (SMS, WhatsApp, Email)
- Records each attempt in `DeliveryLog` with a truthful `success` field
- Returns a structured list — one entry per channel attempted

**Why the contract exists:**
The system must support multiple delivery channels (SMS, WhatsApp, Email, and future channels such as Mandrill email and voice). Without a defined contract, each channel would surface outcomes differently, making it impossible to inspect delivery state, add retry logic, or plug in new providers without touching callers.

The contract decouples channel implementation from caller policy. The caller decides what to do with results; this service only reports what happened.

---

## 2. Function Contract

### Signature

```python
def send_text(
    self,
    user_id: int,
    message: str,
    cbm_id: int | None = None,
) -> list[dict]:
```

| Parameter | Type | Description |
|---|---|---|
| `user_id` | `int` | `UserID` from `AI_ChatBot_TriggerData`. Used to look up phone and email. |
| `message` | `str` | The message body to deliver. |
| `cbm_id` | `int \| None` | The `CBM_ID` of the trigger that initiated this send. Written to `DeliveryLog`. Must be passed by every caller. |

### Return type

`list[dict]` — a list of `DeliveryResult` entries, one per channel attempted.

- Returns an empty list when no delivery is attempted (see Section 4).
- Never returns `True`, `False`, or `None`.
- Never raises an exception to the caller.

---

## 3. DeliveryResult Structure

Each entry in the returned list conforms to this shape:

| Field | Type | Description |
|---|---|---|
| `success` | `bool` | `True` if the provider accepted the send. `False` on any exception. |
| `channel` | `str` | Channel identifier. One of: `"sms"`, `"whatsapp"`, `"email"`. |
| `provider` | `str` | Provider identifier. One of: `"twilio"`, `"smtp"`. Future: `"mandrill"`, `"voice"`. |
| `provider_id` | `str \| None` | Provider's message ID (e.g. Twilio `SID`). `None` if unavailable or send failed. |
| `error` | `str \| None` | Exception message on failure. `None` on success. |
| `recipient` | `str \| None` | Phone number or email address the send was directed to. `None` if address was not resolved before failure. |

### Example — successful SMS send

```python
{
    "success":     True,
    "channel":     "sms",
    "provider":    "twilio",
    "provider_id": "SMa1b2c3d4e5f6",
    "error":       None,
    "recipient":   "+15551234567",
}
```

### Example — failed email send

```python
{
    "success":     False,
    "channel":     "email",
    "provider":    "smtp",
    "provider_id": None,
    "error":       "SMTP connection refused",
    "recipient":   "student@example.com",
}
```

---

## 4. Behavior Rules

### Never return True or False

`send_text()` must return `list[dict]` on every code path. The old `return True` / `return False` pattern is removed. The outer `except` returns `results` (whatever was collected before the exception), not a boolean.

### Always return a list

Even when all channels fail, the function returns a list of failed entries — not an exception, not a boolean, not `None`.

### Empty list conditions

An empty list is returned **only** when:
1. No contact info is available — `phone` and `email` are both `None` after DB lookup and no `OUTBOUND_TEST_PHONE` / `OUTBOUND_TEST_EMAIL` override is set.
2. No channels are configured — Twilio env vars are absent **and** email env vars are absent, so no channel block executes.

If a channel block executes — regardless of outcome — one entry is appended.

### One entry per channel attempted

Each channel block appends exactly one `DeliveryResult` dict after its inner try/except resolves. The append always happens — success or failure. There is no conditional append.

### Channel isolation

Each channel is wrapped in its own inner try/except. A failure in one channel never prevents another channel from executing. The outer try/except is a safety net for unexpected errors in contact lookup or environment variable reads.

---

## 5. Call Sequence and cbm_id Requirement

### Correct call sequence

```
trigger_worker.process_pending_triggers()
  → MentorMessageService.process_trigger(cbm_id)
    → session.get(cbm_id)                    ← read row and evaluate message
    → UPDATE TriggeredUser                   ← atomic claim
        SET Completed=1, CompletedDate=now
        OUTPUT INSERTED.CBM_ID               ← SQL Server
        WHERE CBM_ID=? AND Completed=0       ← only first worker matches
    → claimed_row = result.fetchone()
    → session.commit()
    → if claimed_row is None:
          return {"sent": False, "reason": "already_claimed"}  ← exit, no send
    → AuditLogService().log_event(...)       ← only after claim confirmed
    → EngagementTrackerService().log_event(...)
    → OutboundDeliveryService().send_text(
          user_id=user_id,
          message=message_text,
          cbm_id=cbm_id,        ← required
      )
```

The trigger row is claimed via an atomic `UPDATE ... WHERE Completed=0` with an
`OUTPUT INSERTED` / `RETURNING` clause. Only the worker whose `UPDATE` matches the
`WHERE Completed=0` condition receives a row back from the database. All other
concurrent workers receive `None` from `fetchone()` and return `already_claimed`
before `send_text()` is reached.

This eliminates the duplicate-send race that would occur if two workers both read
`Completed=0` before either commits. The `RETURNING` clause is used instead of
`rowcount` to avoid the `rowcount=-1` ambiguity that arises when `SET NOCOUNT` is
active on the SQL Server connection.

Audit and engagement log writes happen **after** the claim is confirmed, ensuring
a losing worker never writes orphaned records.

Delivery failures are non-blocking. `process_trigger()` wraps `send_text()` in a
`try/except` and returns `{"sent": False}` on exception, but the trigger row
remains permanently completed (`Completed=1`) and is not retried.

### cbm_id threading requirement

`cbm_id` **must** be passed from `process_trigger()` to `send_text()`. Every `DeliveryLog` row written by `send_text()` must carry the `cbm_id` of the originating trigger.

This is the only way to answer: *"For trigger 12345 — what was sent, to whom, and did it succeed?"*

**Do not call `send_text()` without `cbm_id`.** Omitting it produces orphaned `DeliveryLog` rows that cannot be traced back to a trigger.

### DeliveryLog schema (per channel attempt)

```python
DeliveryLog(
    cbm_id        = cbm_id,        # from process_trigger — required
    user_id       = user_id,
    channel       = "sms",         # or "whatsapp", "email"
    success       = True / False,
    error_message = None / "...",
    created_on    = datetime.utcnow(),
)
```

---

## 6. Extensibility — Adding a New Channel

To add a new channel (e.g. Mandrill email, Twilio voice, push notification):

**Step 1 — Add a conditional block** after the existing channel blocks, gated on its required env vars:

```python
mandrill_api_key = os.environ.get("MANDRILL_API_KEY", "")

if mandrill_api_key and email:
    _mandrill_success   = False
    _mandrill_error     = None
    _mandrill_id        = None
    _mandrill_recipient = None
    try:
        # call provider API here
        _mandrill_id        = response["_id"]
        _mandrill_recipient = email
        _mandrill_success   = True
    except Exception as e:
        _mandrill_error = str(e)
    results.append({
        "success":     _mandrill_success,
        "channel":     "mandrill_email",
        "provider":    "mandrill",
        "provider_id": _mandrill_id,
        "error":       _mandrill_error,
        "recipient":   _mandrill_recipient,
    })
    # write DeliveryLog row with cbm_id
```

**Step 2 — Add env var documentation** to this directive.

**Step 3 — Add unit tests** in `tests/unit/test_outbound_delivery_service.py` following the existing pattern:
- Mock the provider client
- Assert the result entry has all 6 fields
- Assert `cbm_id` is written to `DeliveryLog`

**Step 4 — Update Definition of Done** below.

New channels must not change the caller (`process_trigger`). The contract guarantees the caller always receives `list[dict]`.

---

## 7. Non-Goals

This service does **not**:

- **Retry failed sends.** Retry policy belongs to the caller or a dedicated retry worker. `DeliveryLog` provides the data needed to build one.
- **Make provider-specific assumptions in callers.** Callers receive `list[dict]` and must not inspect `provider` to make routing decisions.
- **Handle UI or user-facing error messages.** Console output is for operator observability only.
- **Validate message content.** Content validation belongs to the trigger rule or mentor message layer.
- **Determine which channel to prefer.** All configured channels are attempted. Priority or fallback logic is a future concern and belongs in a routing layer above this service.
- **Throttle or rate-limit sends.** Rate limiting is a provider-level or worker-level concern.

---

## 8. Environment Variables

### Twilio (SMS / WhatsApp)

| Env var | Purpose |
|---|---|
| `TWILIO_ACCOUNT_SID` | Twilio account identifier. All three must be set for SMS/WhatsApp to fire. |
| `TWILIO_AUTH_TOKEN` | Twilio auth token. |
| `TWILIO_FROM_NUMBER` | Sending phone number for SMS. |
| `OUTBOUND_USE_WHATSAPP` | Set to `"1"` to use WhatsApp sandbox. Defaults to SMS. |
| `OUTBOUND_TEST_PHONE` | Override destination phone. Use in all non-production environments. |

### Email (SMTP)

| Env var | Purpose |
|---|---|
| `EMAIL_HOST` | SMTP server hostname. All three must be set for email to fire. |
| `EMAIL_FROM` | Sender email address. |
| `EMAIL_PASSWORD` | Sender SMTP credential. |
| `OUTBOUND_TEST_EMAIL` | Override destination email. Use in all non-production environments. |

---

## 9. Testability Requirements

- Mock `twilio.rest.Client` — no real Twilio calls in unit tests
- Mock `smtplib.SMTP_SSL` — no real SMTP connections in unit tests
- Patch `module.SessionLocal = None` to skip DB lookup when contact data is irrelevant
- Use `OUTBOUND_TEST_PHONE` / `OUTBOUND_TEST_EMAIL` via `monkeypatch.setenv` to supply contact without a DB record
- For `DeliveryLog` write verification — use the real local SQLite `SessionLocal`; clean up in `finally`

---

## 10. Definition of Done

- [x] `OutboundDeliveryService.send_text()` returns `list[dict]` on all code paths
- [x] Each result entry contains all 6 contract fields: `success`, `channel`, `provider`, `provider_id`, `error`, `recipient`
- [x] `cbm_id` parameter added to `send_text()` signature
- [x] `cbm_id` written to every `DeliveryLog` row
- [x] `cbm_id` forwarded from `process_trigger()` to `send_text()`
- [x] `Completed=1` claimed via atomic `UPDATE ... WHERE Completed=0 RETURNING CBM_ID` before `send_text()` is called
- [x] Concurrent workers that lose the atomic claim return `already_claimed` without calling `send_text()`
- [x] `RETURNING` clause used instead of `rowcount` to eliminate `SET NOCOUNT` ambiguity
- [x] SMS channel implemented and unit tested
- [x] WhatsApp channel implemented and unit tested
- [x] Email (SMTP) channel implemented and unit tested
- [x] `DeliveryResult` structure verified by unit test
- [x] `DeliveryLog.cbm_id` write verified by unit test against local SQLite
- [x] No provider credentials required for tests to pass
- [x] No secrets in repository
- [ ] Mandrill email channel (future)
- [ ] Voice channel (future)
- [ ] Retry worker consuming `DeliveryLog` (future)
