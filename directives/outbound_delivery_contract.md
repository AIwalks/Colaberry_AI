# Directive: Outbound Delivery Contract

## 1. Purpose

`OutboundDeliveryService` is the single outbound channel adapter for the Colaberry AI system. It is called by `MentorMessageService.process_trigger()` after a trigger row is processed and logged. Its job is to deliver a message to the student via SMS, WhatsApp, or Email.

**Supported delivery channels:**

| Channel | Transport | Credentials |
|---|---|---|
| SMS | Twilio REST API | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` |
| WhatsApp | Twilio REST API (sandbox) | Same as SMS + `OUTBOUND_USE_WHATSAPP=1` |
| Email | SMTP SSL (stdlib `smtplib`) | `EMAIL_HOST`, `EMAIL_FROM`, `EMAIL_PASSWORD` |

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
| `Email` | Destination address for Email delivery |
| `FirstName` + `LastName` | Logged in audit print |

If `SessionLocal` is `None` (no DB configured), the lookup is skipped and both `phone` and `email` remain `None`.

---

## 4. Test Overrides

If `OUTBOUND_TEST_PHONE` is set, it replaces the student's real phone number for all sends.
If `OUTBOUND_TEST_EMAIL` is set, it replaces the student's real email address for all sends.
Both overrides allow safe end-to-end testing without delivering to real students.

```
test_phone = os.environ.get("OUTBOUND_TEST_PHONE", "")
if test_phone:
    phone = test_phone   # overrides DB value

test_email = os.environ.get("OUTBOUND_TEST_EMAIL", "")
if test_email:
    email = test_email   # overrides DB value
```

Console lines are printed when overrides are active:
```
[OutboundDeliveryService] TEST OVERRIDE phone='...'
[OutboundDeliveryService] TEST OVERRIDE email='...'
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

### Twilio (SMS / WhatsApp)

| Env var | Required | Purpose |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | No | Twilio account identifier. If absent, Twilio call is skipped silently. |
| `TWILIO_AUTH_TOKEN` | No | Twilio auth token. If absent, Twilio call is skipped silently. |
| `TWILIO_FROM_NUMBER` | No | Sending phone number for SMS. If absent, Twilio call is skipped silently. |
| `OUTBOUND_USE_WHATSAPP` | No | Set to `"1"` to use WhatsApp sandbox. Defaults to SMS. |
| `OUTBOUND_TEST_PHONE` | No | Override destination phone. Recommended for all non-production environments. |

All three Twilio vars must be present and non-empty, **and** `phone` must be non-None, for a send to be attempted. Any missing value silently skips the Twilio call and returns `True`.

### Email (SMTP)

| Env var | Required | Purpose |
|---|---|---|
| `EMAIL_HOST` | No | SMTP server hostname. If absent, email send is skipped silently. |
| `EMAIL_FROM` | No | Sender email address. If absent, email send is skipped silently. |
| `EMAIL_PASSWORD` | No | Sender credential for SMTP login. If absent, email send is skipped silently. |
| `OUTBOUND_TEST_EMAIL` | No | Override destination email. Recommended for all non-production environments. |

All three email vars must be present and non-empty, **and** `email` must be non-None, for a send to be attempted. Any missing value silently skips the email send and returns `True`.

---

## 7. Non-Blocking Failure Behaviour

Every channel is wrapped in its own inner try/except. A failure in one channel never prevents another channel from attempting delivery.

```python
# Inner — Twilio errors are caught and printed, never re-raised
try:
    msg = Client(...).messages.create(...)
    print(f"[TWILIO SENT] sid={msg.sid}")
except Exception as e:
    print(f"[TWILIO ERROR] {e}")

# Inner — Email errors are caught and printed, never re-raised
try:
    with smtplib.SMTP_SSL(email_host) as server:
        server.login(email_from, email_password)
        server.sendmail(email_from, email, msg.as_string())
    print(f"[EMAIL SENT] to={email!r}")
except Exception as e:
    print(f"[EMAIL ERROR] {e}")

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
[OutboundDeliveryService] TEST OVERRIDE email='test@example.com'
[OutboundDeliveryService][TWILIO SENT] sid=SMxxxxxxxx
[OutboundDeliveryService][TWILIO ERROR] <exception message>
[OutboundDeliveryService][EMAIL SENT] to='student@example.com'
[OutboundDeliveryService][EMAIL ERROR] <exception message>
```

---

## 9. Testability Requirements

- All unit tests must mock `twilio.rest.Client` — no real Twilio calls
- All unit tests must mock `smtplib.SMTP_SSL` — no real SMTP connections
- `SessionLocal` must be patchable to `None` to skip DB lookup
- `OUTBOUND_TEST_PHONE` and `OUTBOUND_TEST_EMAIL` must be settable via `monkeypatch.setenv`
- Tests must not depend on network, Twilio account, SMTP server, or real student data

See: `tests/unit/test_outbound_delivery_service.py`

---

## 10. Definition of Done

- [x] `OutboundDeliveryService` exists at `services/outbound_delivery_service.py`
- [x] SMS and WhatsApp branches implemented and unit tested
- [x] Email branch implemented and unit tested
- [x] `OUTBOUND_TEST_PHONE` override implemented and unit tested
- [x] `OUTBOUND_TEST_EMAIL` override implemented and unit tested
- [x] Delivery failure is non-blocking — never propagates to trigger worker
- [x] Called by `MentorMessageService.process_trigger()` before `Completed=1`
- [x] No Twilio credentials required for tests to pass
- [x] No SMTP credentials required for tests to pass
- [x] No secrets in repository
