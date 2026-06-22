"""Unit tests for OutboundDeliveryService."""

import contextlib
from unittest.mock import MagicMock, patch


class TestOutboundDeliveryServiceWhatsApp:

    def test_whatsapp_branch_uses_whatsapp_prefix(self, monkeypatch):
        """When OUTBOUND_USE_WHATSAPP=1, to/from must use whatsapp: prefix."""
        monkeypatch.setenv("OUTBOUND_USE_WHATSAPP",   "1")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID",      "ACtest")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN",        "authtest")
        monkeypatch.setenv("TWILIO_FROM_NUMBER",       "+15550000000")
        monkeypatch.setenv("OUTBOUND_TEST_PHONE",      "+15551234567")

        captured = {}

        mock_msg = MagicMock()
        mock_msg.sid = "SMtest123"

        def fake_create(**kwargs):
            captured.update(kwargs)
            return mock_msg

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.side_effect = fake_create

        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", None)  # skip DB lookup

        with patch("twilio.rest.Client", return_value=mock_client_instance):
            from services.outbound_delivery_service import OutboundDeliveryService
            result = OutboundDeliveryService().send_text(user_id=1, message="Hello")

        assert isinstance(result, list)
        assert captured.get("to",     "").startswith("whatsapp:"), \
            f"Expected to= to start with 'whatsapp:', got {captured.get('to')!r}"
        assert captured.get("from_",  "").startswith("whatsapp:"), \
            f"Expected from_= to start with 'whatsapp:', got {captured.get('from_')!r}"
        assert captured.get("to")    == "whatsapp:+15551234567"
        assert captured.get("from_") == "whatsapp:+14155238886"

    def test_sms_branch_does_not_use_whatsapp_prefix(self, monkeypatch):
        """When OUTBOUND_USE_WHATSAPP is unset, to/from must NOT use whatsapp: prefix."""
        monkeypatch.delenv("OUTBOUND_USE_WHATSAPP", raising=False)
        monkeypatch.setenv("TWILIO_ACCOUNT_SID",   "ACtest")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN",     "authtest")
        monkeypatch.setenv("TWILIO_FROM_NUMBER",    "+15550000000")
        monkeypatch.setenv("OUTBOUND_TEST_PHONE",   "+15551234567")

        captured = {}

        mock_msg = MagicMock()
        mock_msg.sid = "SMtest456"

        def fake_create(**kwargs):
            captured.update(kwargs)
            return mock_msg

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.side_effect = fake_create

        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", None)

        with patch("twilio.rest.Client", return_value=mock_client_instance):
            from services.outbound_delivery_service import OutboundDeliveryService
            result = OutboundDeliveryService().send_text(user_id=1, message="Hello")

        assert isinstance(result, list)
        assert not captured.get("to",    "").startswith("whatsapp:")
        assert not captured.get("from_", "").startswith("whatsapp:")
        assert captured.get("to")    == "+15551234567"
        assert captured.get("from_") == "+15550000000"


class TestOutboundDeliveryServiceEmail:

    def test_email_sent_when_email_and_env_vars_present(self, monkeypatch):
        """Email is sent when all 3 env vars and a destination email are set."""
        monkeypatch.setenv("EMAIL_HOST",     "smtp.example.com")
        monkeypatch.setenv("EMAIL_FROM",     "sender@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "secret")
        monkeypatch.setenv("OUTBOUND_TEST_EMAIL", "test@example.com")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)

        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", None)

        mock_server = MagicMock()
        mock_smtp_ssl = MagicMock(return_value=__import__("contextlib").nullcontext(mock_server))

        with patch("smtplib.SMTP_SSL", mock_smtp_ssl):
            from services.outbound_delivery_service import OutboundDeliveryService
            result = OutboundDeliveryService().send_text(user_id=1, message="Hello email")

        assert isinstance(result, list)
        mock_server.login.assert_called_once_with("sender@example.com", "secret")
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert args[0] == "sender@example.com"
        assert args[1] == "test@example.com"

    def test_email_not_sent_when_email_is_none(self, monkeypatch):
        """Email block is skipped when student has no email and no override is set."""
        monkeypatch.setenv("EMAIL_HOST",     "smtp.example.com")
        monkeypatch.setenv("EMAIL_FROM",     "sender@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "secret")
        monkeypatch.delenv("OUTBOUND_TEST_EMAIL", raising=False)
        monkeypatch.delenv("TWILIO_ACCOUNT_SID",  raising=False)

        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", None)  # email stays None

        with patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
            from services.outbound_delivery_service import OutboundDeliveryService
            result = OutboundDeliveryService().send_text(user_id=1, message="Hello")

        assert isinstance(result, list)
        mock_smtp_ssl.assert_not_called()

    def test_email_not_sent_when_env_vars_missing(self, monkeypatch):
        """Email block is skipped when any of the 3 required env vars is absent."""
        monkeypatch.setenv("OUTBOUND_TEST_EMAIL", "test@example.com")
        monkeypatch.delenv("EMAIL_HOST",     raising=False)
        monkeypatch.delenv("EMAIL_FROM",     raising=False)
        monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)

        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", None)

        with patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
            from services.outbound_delivery_service import OutboundDeliveryService
            result = OutboundDeliveryService().send_text(user_id=1, message="Hello")

        assert isinstance(result, list)
        mock_smtp_ssl.assert_not_called()

    def test_outbound_test_email_overrides_student_email(self, monkeypatch):
        """OUTBOUND_TEST_EMAIL replaces whatever email came from the DB."""
        monkeypatch.setenv("EMAIL_HOST",          "smtp.example.com")
        monkeypatch.setenv("EMAIL_FROM",          "sender@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD",      "secret")
        monkeypatch.setenv("OUTBOUND_TEST_EMAIL", "override@example.com")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID",  raising=False)

        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", None)

        mock_server = MagicMock()
        mock_smtp_ssl = MagicMock(return_value=__import__("contextlib").nullcontext(mock_server))

        with patch("smtplib.SMTP_SSL", mock_smtp_ssl):
            from services.outbound_delivery_service import OutboundDeliveryService
            OutboundDeliveryService().send_text(user_id=1, message="Hello")

        args = mock_server.sendmail.call_args[0]
        assert args[1] == "override@example.com", (
            f"Expected override@example.com, got {args[1]!r}"
        )

    def test_email_failure_does_not_raise(self, monkeypatch):
        """An SMTP exception is caught; send_text() still returns a list."""
        monkeypatch.setenv("EMAIL_HOST",          "smtp.example.com")
        monkeypatch.setenv("EMAIL_FROM",          "sender@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD",      "secret")
        monkeypatch.setenv("OUTBOUND_TEST_EMAIL", "test@example.com")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID",  raising=False)

        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", None)

        with patch("smtplib.SMTP_SSL", side_effect=Exception("SMTP connection refused")):
            from services.outbound_delivery_service import OutboundDeliveryService
            result = OutboundDeliveryService().send_text(user_id=1, message="Hello")

        assert isinstance(result, list)

    def test_sms_and_email_both_fire_when_credentials_present(self, monkeypatch):
        """Both Twilio and email blocks execute independently in the same call."""
        monkeypatch.setenv("TWILIO_ACCOUNT_SID",  "ACtest")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN",    "authtest")
        monkeypatch.setenv("TWILIO_FROM_NUMBER",   "+15550000000")
        monkeypatch.setenv("OUTBOUND_TEST_PHONE",  "+15551234567")
        monkeypatch.setenv("EMAIL_HOST",           "smtp.example.com")
        monkeypatch.setenv("EMAIL_FROM",           "sender@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD",       "secret")
        monkeypatch.setenv("OUTBOUND_TEST_EMAIL",  "test@example.com")
        monkeypatch.delenv("OUTBOUND_USE_WHATSAPP", raising=False)

        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", None)

        mock_twilio_msg = MagicMock()
        mock_twilio_msg.sid = "SMdual"
        mock_twilio_instance = MagicMock()
        mock_twilio_instance.messages.create.return_value = mock_twilio_msg

        mock_server = MagicMock()
        mock_smtp_ssl = MagicMock(return_value=__import__("contextlib").nullcontext(mock_server))

        with patch("twilio.rest.Client", return_value=mock_twilio_instance), \
             patch("smtplib.SMTP_SSL", mock_smtp_ssl):
            from services.outbound_delivery_service import OutboundDeliveryService
            result = OutboundDeliveryService().send_text(user_id=1, message="Dual send")

        assert len(result) == 2
        mock_twilio_instance.messages.create.assert_called_once()
        mock_server.sendmail.assert_called_once()


class TestDeliveryContract:

    def test_send_text_returns_structured_list(self, monkeypatch):
        """send_text() must return a list of dicts, not a bool.

        Each entry must contain all 6 contract fields:
        success, channel, provider, provider_id, error, recipient.
        """
        monkeypatch.delenv("OUTBOUND_USE_WHATSAPP", raising=False)
        monkeypatch.setenv("TWILIO_ACCOUNT_SID",   "ACtest")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN",     "authtest")
        monkeypatch.setenv("TWILIO_FROM_NUMBER",    "+15550000000")
        monkeypatch.setenv("OUTBOUND_TEST_PHONE",   "+15559990001")
        monkeypatch.delenv("EMAIL_HOST", raising=False)

        mock_msg = MagicMock()
        mock_msg.sid = "SMcontract01"
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_msg

        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", None)

        with patch("twilio.rest.Client", return_value=mock_client_instance):
            from services.outbound_delivery_service import OutboundDeliveryService
            result = OutboundDeliveryService().send_text(user_id=1, message="contract test")

        assert isinstance(result, list), \
            f"send_text() must return list, got {type(result).__name__}"
        assert len(result) == 1, \
            f"Expected 1 result entry for SMS channel, got {len(result)}"

        entry = result[0]
        required_keys = {"success", "channel", "provider", "provider_id", "error", "recipient"}
        missing = required_keys - entry.keys()
        assert not missing, f"Result entry missing required keys: {missing}"

        assert entry["success"]      is True
        assert entry["channel"]      == "sms"
        assert entry["provider"]     == "twilio"
        assert entry["provider_id"]  == "SMcontract01"
        assert entry["error"]        is None
        assert entry["recipient"]    == "+15559990001"

    def test_cbm_id_written_to_delivery_log(self, monkeypatch):
        """send_text(..., cbm_id=999) must write a DeliveryLog row with cbm_id=999.

        Uses local SQLite — no real email is sent (SMTP_SSL is mocked).
        Cleans up after regardless of assertion outcome.
        """
        _CBM_ID = 999

        monkeypatch.setenv("EMAIL_HOST",          "smtp.example.com")
        monkeypatch.setenv("EMAIL_FROM",          "sender@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD",      "secret")
        monkeypatch.setenv("OUTBOUND_TEST_EMAIL", "contract@example.com")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID",  raising=False)

        mock_server = MagicMock()
        mock_smtp_ssl = MagicMock(
            return_value=__import__("contextlib").nullcontext(mock_server)
        )

        try:
            with patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                from services.outbound_delivery_service import OutboundDeliveryService
                result = OutboundDeliveryService().send_text(
                    user_id=1,
                    message="cbm_id log test",
                    cbm_id=_CBM_ID,
                )

            assert isinstance(result, list), "send_text() must return list"
            assert len(result) == 1

            from config.database import SessionLocal
            from services.models import DeliveryLog
            with SessionLocal() as session:
                row = (
                    session.query(DeliveryLog)
                    .filter_by(cbm_id=_CBM_ID)
                    .order_by(DeliveryLog.id.desc())
                    .first()
                )
            assert row is not None, \
                f"No DeliveryLog row found with cbm_id={_CBM_ID}"
            assert row.cbm_id == _CBM_ID, \
                f"Expected cbm_id={_CBM_ID}, got {row.cbm_id}"
            assert row.channel == "email"

        finally:
            from config.database import SessionLocal
            from services.models import DeliveryLog
            with SessionLocal() as session:
                session.query(DeliveryLog).filter_by(cbm_id=_CBM_ID).delete()
                session.commit()


class TestNudgeSentEngagementEvent:
    """Verify that a nudge_sent EngagementEvent is written after successful delivery."""

    # ------------------------------------------------------------------
    # Session mock shared across tests in this class
    # ------------------------------------------------------------------

    @staticmethod
    def _make_session_factory():
        """Return (factory, added_objects_list).

        factory() creates a new fake session on each call.
        added_objects_list accumulates every obj passed to session.add().
        """
        added = []

        class _FakeSession:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get(self, model_class, pk): return None
            def add(self, obj): added.append(obj)
            def commit(self): pass

        return _FakeSession, added

    # ------------------------------------------------------------------
    # WhatsApp: thread_id == Twilio message SID
    # ------------------------------------------------------------------

    def test_whatsapp_success_writes_nudge_sent_with_stable_wa_key(self, monkeypatch):
        """WhatsApp success → EngagementEvent with thread_id='wa:{user_id}' (not msg.sid).

        ThreadIdMatcher requires the same thread_id on both the outbound nudge_sent
        event and the inbound reply event.  Twilio assigns a new MessageSid to every
        message, so msg.sid cannot serve as a stable thread identifier.  The stable
        key 'wa:{user_id}' is derived from user_id, which is present on both sides.
        """
        monkeypatch.setenv("OUTBOUND_USE_WHATSAPP",  "1")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID",     "ACtest")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN",       "authtest")
        monkeypatch.setenv("TWILIO_FROM_NUMBER",      "+15550000000")
        monkeypatch.setenv("OUTBOUND_TEST_PHONE",     "+15551234567")
        monkeypatch.delenv("EMAIL_HOST", raising=False)

        mock_msg = MagicMock()
        mock_msg.sid = "WA_SID_001"
        mock_twilio = MagicMock()
        mock_twilio.messages.create.return_value = mock_msg

        factory, added = self._make_session_factory()
        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", factory)

        with patch("twilio.rest.Client", return_value=mock_twilio):
            from services.outbound_delivery_service import OutboundDeliveryService
            OutboundDeliveryService().send_text(user_id=1, message="Hello", cbm_id=42)

        from services.models import EngagementEvent
        nudge_events = [o for o in added if isinstance(o, EngagementEvent)]
        assert len(nudge_events) == 1, f"Expected 1 nudge_sent event, got {len(nudge_events)}"
        evt = nudge_events[0]
        assert evt.event_type == "nudge_sent"
        assert evt.trigger_id == 42
        assert evt.thread_id  == "wa:1"   # stable key — NOT the Twilio msg.sid
        assert evt.channel    == "whatsapp"
        assert evt.user_id    == 1
        assert evt.agent_name == "OutboundDeliveryService"

    def test_whatsapp_thread_id_is_not_message_sid(self, monkeypatch):
        """thread_id must never equal the Twilio MessageSid for WhatsApp nudges."""
        monkeypatch.setenv("OUTBOUND_USE_WHATSAPP",  "1")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID",     "ACtest")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN",       "authtest")
        monkeypatch.setenv("TWILIO_FROM_NUMBER",      "+15550000000")
        monkeypatch.setenv("OUTBOUND_TEST_PHONE",     "+15551234567")
        monkeypatch.delenv("EMAIL_HOST", raising=False)

        mock_msg = MagicMock()
        mock_msg.sid = "SMunique_per_message_sid"
        mock_twilio = MagicMock()
        mock_twilio.messages.create.return_value = mock_msg

        factory, added = self._make_session_factory()
        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", factory)

        with patch("twilio.rest.Client", return_value=mock_twilio):
            from services.outbound_delivery_service import OutboundDeliveryService
            OutboundDeliveryService().send_text(user_id=7, message="Hello", cbm_id=42)

        from services.models import EngagementEvent
        nudge_events = [o for o in added if isinstance(o, EngagementEvent)]
        assert len(nudge_events) == 1
        evt = nudge_events[0]
        assert evt.thread_id != "SMunique_per_message_sid", (
            "thread_id must be a stable conversation key, not the per-message Twilio SID"
        )
        assert evt.thread_id == "wa:7"

    # ------------------------------------------------------------------
    # SMS: no thread_id (SMS does not support threading per directive §3)
    # ------------------------------------------------------------------

    def test_sms_success_writes_nudge_sent_without_thread_id(self, monkeypatch):
        """SMS success → EngagementEvent with thread_id=None."""
        monkeypatch.delenv("OUTBOUND_USE_WHATSAPP", raising=False)
        monkeypatch.setenv("TWILIO_ACCOUNT_SID",    "ACtest")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN",      "authtest")
        monkeypatch.setenv("TWILIO_FROM_NUMBER",     "+15550000000")
        monkeypatch.setenv("OUTBOUND_TEST_PHONE",    "+15551234567")
        monkeypatch.delenv("EMAIL_HOST", raising=False)

        mock_msg = MagicMock()
        mock_msg.sid = "SMS_SID_001"
        mock_twilio = MagicMock()
        mock_twilio.messages.create.return_value = mock_msg

        factory, added = self._make_session_factory()
        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", factory)

        with patch("twilio.rest.Client", return_value=mock_twilio):
            from services.outbound_delivery_service import OutboundDeliveryService
            OutboundDeliveryService().send_text(user_id=1, message="Hello", cbm_id=42)

        from services.models import EngagementEvent
        nudge_events = [o for o in added if isinstance(o, EngagementEvent)]
        assert len(nudge_events) == 1
        evt = nudge_events[0]
        assert evt.event_type == "nudge_sent"
        assert evt.trigger_id == 42
        assert evt.thread_id  is None
        assert evt.channel    == "sms"

    # ------------------------------------------------------------------
    # Email: no thread_id
    # ------------------------------------------------------------------

    def test_email_success_writes_nudge_sent_without_thread_id(self, monkeypatch):
        """Email success → EngagementEvent with thread_id=None."""
        monkeypatch.setenv("EMAIL_HOST",          "smtp.example.com")
        monkeypatch.setenv("EMAIL_FROM",          "sender@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD",      "secret")
        monkeypatch.setenv("OUTBOUND_TEST_EMAIL", "student@example.com")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID",  raising=False)

        mock_server = MagicMock()

        factory, added = self._make_session_factory()
        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", factory)

        with patch("smtplib.SMTP_SSL",
                   MagicMock(return_value=contextlib.nullcontext(mock_server))):
            from services.outbound_delivery_service import OutboundDeliveryService
            OutboundDeliveryService().send_text(user_id=1, message="Hello", cbm_id=42)

        from services.models import EngagementEvent
        nudge_events = [o for o in added if isinstance(o, EngagementEvent)]
        assert len(nudge_events) == 1
        evt = nudge_events[0]
        assert evt.event_type == "nudge_sent"
        assert evt.trigger_id == 42
        assert evt.thread_id  is None
        assert evt.channel    == "email"

    # ------------------------------------------------------------------
    # No cbm_id → no EngagementEvent
    # ------------------------------------------------------------------

    def test_nudge_sent_not_written_when_cbm_id_is_none(self, monkeypatch):
        """When cbm_id is not supplied, no nudge_sent EngagementEvent is written."""
        monkeypatch.delenv("OUTBOUND_USE_WHATSAPP", raising=False)
        monkeypatch.setenv("TWILIO_ACCOUNT_SID",    "ACtest")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN",      "authtest")
        monkeypatch.setenv("TWILIO_FROM_NUMBER",     "+15550000000")
        monkeypatch.setenv("OUTBOUND_TEST_PHONE",    "+15551234567")
        monkeypatch.delenv("EMAIL_HOST", raising=False)

        mock_msg = MagicMock()
        mock_msg.sid = "SMS_SID_nocbm"
        mock_twilio = MagicMock()
        mock_twilio.messages.create.return_value = mock_msg

        factory, added = self._make_session_factory()
        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", factory)

        with patch("twilio.rest.Client", return_value=mock_twilio):
            from services.outbound_delivery_service import OutboundDeliveryService
            OutboundDeliveryService().send_text(user_id=1, message="Hello")  # cbm_id=None

        from services.models import EngagementEvent
        nudge_events = [o for o in added if isinstance(o, EngagementEvent)]
        assert len(nudge_events) == 0, (
            f"Expected no nudge_sent event when cbm_id=None, got {len(nudge_events)}"
        )

    # ------------------------------------------------------------------
    # Delivery failure → no EngagementEvent
    # ------------------------------------------------------------------

    def test_nudge_sent_not_written_on_delivery_failure(self, monkeypatch):
        """When the Twilio send raises an exception, no nudge_sent event is written."""
        monkeypatch.delenv("OUTBOUND_USE_WHATSAPP", raising=False)
        monkeypatch.setenv("TWILIO_ACCOUNT_SID",    "ACtest")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN",      "authtest")
        monkeypatch.setenv("TWILIO_FROM_NUMBER",     "+15550000000")
        monkeypatch.setenv("OUTBOUND_TEST_PHONE",    "+15551234567")
        monkeypatch.delenv("EMAIL_HOST", raising=False)

        mock_twilio = MagicMock()
        mock_twilio.messages.create.side_effect = Exception("Twilio unavailable")

        factory, added = self._make_session_factory()
        import services.outbound_delivery_service as module
        monkeypatch.setattr(module, "SessionLocal", factory)

        with patch("twilio.rest.Client", return_value=mock_twilio):
            from services.outbound_delivery_service import OutboundDeliveryService
            result = OutboundDeliveryService().send_text(user_id=1, message="Hello", cbm_id=42)

        assert isinstance(result, list)
        from services.models import EngagementEvent
        nudge_events = [o for o in added if isinstance(o, EngagementEvent)]
        assert len(nudge_events) == 0, (
            f"Expected no nudge_sent event on delivery failure, got {len(nudge_events)}"
        )
