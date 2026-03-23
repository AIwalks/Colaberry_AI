"""Unit tests for OutboundDeliveryService."""

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

        assert result is True
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

        assert result is True
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

        assert result is True
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

        assert result is True
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

        assert result is True
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
        """An SMTP exception is caught; send_text() still returns True."""
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

        assert result is True

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

        assert result is True
        mock_twilio_instance.messages.create.assert_called_once()
        mock_server.sendmail.assert_called_once()
