# Directive: Outbound Delivery Contract

## 1. Purpose

`OutboundDeliveryService` is the single outbound channel adapter for the Colaberry AI system. It is called by `MentorMessageService.process_trigger()` after a trigger row is processed and logged. Its job is to deliver a text message to the student via SMS or WhatsApp using Twilio.

The service is intentionally decoupled from the trigger worker. Delivery failures must never prevent a trigger row from being marked `Completed=1`.

---

## 2. When It Is Called

```
trigger_worker.process_pending_triggers()
  → MentorMessageService.process_trigger(cbm_id)
    → OutboundDeliveryService.send_text(user_id, message)
    → triggered.Completed = 1
    → triggered.CompletedDate = datetime.utcnow()
    → session.commit()
```

`send_text()` is called **before** `Completed` is stamped. If delivery fails, the row is still marked complete. Delivery is best-effort.

---

## 3. Student Contact Lookup

`send_text()` looks up the student's contact details from `AI_ChatBot_TriggerData` using `user_id`:

| Field read | Used for |
|---|---|
| `PhoneNumber` | Destination address for SMS or WhatsApp |
| `Email` | Logged in audit print (not yet used for delivery) |
| `FirstName` + `LastName` | Logged in audit print |

If `SessionLocal` is `None` (no DB configured), the lookup is skipped and `phone` remains `None`.

---

## 4. Test Phone Override

If `OUTBOUND_TEST_PHONE` is set, it replaces the student's real phone number for all sends. This allows safe end-to-end testing without delivering to real students.

```
test_phone = os.environ.get("OUTBOUND_TEST_PHONE", "")
if test_phone:
    phone = test_phone   # overrides DB value
```

A console line is printed when the override is active:
```
[OutboundDeliveryService] TEST OVERRIDE phone='...'
```

---

## 5. SMS vs WhatsApp Behavior

Controlled by the `OUTBOUND_USE_WHATSAPP` env var.

| `OUTBOUND_USE_WHATSAPP` | `from_` | `to` |
|---|---|---|
| unset or `"0"` | `TWILIO_FROM_NUMBER` | `phone` |
| `"1"` | `"whatsapp:+14155238886"` (sandbox) | `"whatsapp:{phone}"` |

The WhatsApp sandbox number `+14155238886` is the Twilio development sandbox. Replace with a production WhatsApp sender when provisioned.

---

## 6. Environment Variables

| Env var | Required | Purpose |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | No | Twilio account identifier. If absent, Twilio call is skipped silently. |
| `TWILIO_AUTH_TOKEN` | No | Twilio auth token. If absent, Twilio call is skipped silently. |
| `TWILIO_FROM_NUMBER` | No | Sending phone number for SMS. If absent, Twilio call is skipped silently. |
| `OUTBOUND_USE_WHATSAPP` | No | Set to `"1"` to use WhatsApp sandbox. Defaults to SMS. |
| `OUTBOUND_TEST_PHONE` | No | Override destination phone. Recommended for all non-production environments. |

All three Twilio vars must be present and non-empty, **and** `phone` must be non-None, for a send to be attempted. Any missing value silently skips the Twilio call and returns `True`.

---

## 7. Non-Blocking Failure Behaviour

Delivery is wrapped in two levels of exception handling:

```python
# Inner — Twilio errors are caught and printed, never re-raised
try:
    msg = Client(...).messages.create(...)
    print(f"[TWILIO SENT] sid={msg.sid}")
except Exception as e:
    print(f"[TWILIO ERROR] {e}")

# Outer — any other error returns False without propagating
except Exception:
    return False
```

**The trigger worker is never interrupted by a delivery failure.** `process_trigger()` proceeds to stamp `Completed=1` regardless of whether `send_text()` returns `True` or `False`.

---

## 8. Console Output

Every call to `send_text()` produces at least one console line regardless of delivery outcome:

```
[OutboundDeliveryService] user_id=46828 name='John Doe' phone='+15551234567' email='...' message='...'
```

Additional lines when applicable:
```
[OutboundDeliveryService] TEST OVERRIDE phone='+15550000000'
[OutboundDeliveryService][TWILIO SENT] sid=SMxxxxxxxx
[OutboundDeliveryService][TWILIO ERROR] <exception message>
```

---

## 9. Testability Requirements

- All unit tests must mock `twilio.rest.Client` — no real Twilio calls
- `SessionLocal` must be patchable to `None` to skip DB lookup
- `OUTBOUND_TEST_PHONE` must be settable via `monkeypatch.setenv`
- Tests must not depend on network, Twilio account, or real student data

See: `tests/unit/test_outbound_delivery_service.py`

---

## 10. Definition of Done

- [x] `OutboundDeliveryService` exists at `services/outbound_delivery_service.py`
- [x] SMS and WhatsApp branches implemented and unit tested
- [x] `OUTBOUND_TEST_PHONE` override implemented and unit tested
- [x] Delivery failure is non-blocking — never propagates to trigger worker
- [x] Called by `MentorMessageService.process_trigger()` before `Completed=1`
- [x] No Twilio credentials required for tests to pass
- [x] No secrets in repository
