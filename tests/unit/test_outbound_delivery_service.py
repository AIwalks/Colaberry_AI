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
