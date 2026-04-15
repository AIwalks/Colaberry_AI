"""Outbound delivery service — stub implementation.

Real delivery (Twilio SMS, email, etc.) will replace the print stub
when channel credentials are available. The interface is intentionally
kept stable so callers do not need to change when the real implementation
is wired in.
"""

import os
from datetime import datetime
from config.database import SessionLocal
from services.models import DeliveryLog, TriggerData


class OutboundDeliveryService:

    def send_text(self, user_id: int, message: str, cbm_id: int | None = None) -> list[dict]:
        """Send a text message to a student.

        Parameters
        ----------
        user_id : int
            The UserID from AI_ChatBot_TriggerData.
        message : str
            The message text to deliver.
        cbm_id : int | None
            The CBM_ID of the trigger that caused this send. Written to DeliveryLog.

        Returns
        -------
        list[dict] — one DeliveryResult entry per attempted channel.
        Empty only when no contact info is found or no channels are configured.

        Each entry shape:
            success      bool        — did the provider accept the send?
            channel      str         — "sms" | "whatsapp" | "email"
            provider     str         — "twilio" | "smtp"
            provider_id  str | None  — Twilio SID; None if unavailable
            error        str | None  — exception message on failure; None on success
            recipient    str | None  — phone or email actually sent to
        """
        results: list[dict] = []
        try:
            phone = None
            email = None
            name  = None

            if SessionLocal is not None:
                with SessionLocal() as session:
                    student: TriggerData | None = (
                        session.get(TriggerData, user_id) if user_id is not None else None
                    )
                    if student is not None:
                        phone = student.PhoneNumber
                        email = student.Email
                        name  = f"{student.FirstName} {student.LastName}".strip()

            test_phone = os.environ.get("OUTBOUND_TEST_PHONE", "")
            if test_phone:
                print(f"[OutboundDeliveryService] TEST OVERRIDE phone={test_phone!r}")
                phone = test_phone

            print(
                f"[OutboundDeliveryService] user_id={user_id} name={name!r} "
                f"phone={phone!r} email={email!r} message={message!r}"
            )

            account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
            auth_token  = os.environ.get("TWILIO_AUTH_TOKEN", "")
            from_number = os.environ.get("TWILIO_FROM_NUMBER", "")

            # Integration point — _send_twilio_sms() / _send_twilio_whatsapp():
            # When SMS/WhatsApp adapters are activated, this block is replaced by:
            #   if os.environ.get("OUTBOUND_USE_WHATSAPP") == "1":
            #       results.append(self._send_twilio_whatsapp(phone=phone, message=message))
            #   else:
            #       results.append(self._send_twilio_sms(phone=phone, message=message))
            if account_sid and auth_token and from_number and phone:
                _twilio_channel   = "whatsapp" if os.environ.get("OUTBOUND_USE_WHATSAPP") == "1" else "sms"
                _twilio_success   = False
                _twilio_error     = None
                _twilio_sid       = None
                _twilio_recipient = None
                try:
                    from twilio.rest import Client
                    use_whatsapp = _twilio_channel == "whatsapp"
                    if use_whatsapp:
                        from_addr = "whatsapp:+14155238886"
                        to_addr   = f"whatsapp:{phone}"
                    else:
                        from_addr = from_number
                        to_addr   = phone
                    _twilio_recipient = to_addr
                    msg = Client(account_sid, auth_token).messages.create(
                        body=message,
                        from_=from_addr,
                        to=to_addr,
                    )
                    print(f"[OutboundDeliveryService][TWILIO SENT] sid={msg.sid}")
                    _twilio_success = True
                    _twilio_sid     = msg.sid
                except Exception as e:
                    _twilio_error = str(e)
                    print(f"[OutboundDeliveryService][TWILIO ERROR] {e}")
                results.append({
                    "success":     _twilio_success,
                    "channel":     _twilio_channel,
                    "provider":    "twilio",
                    "provider_id": _twilio_sid,
                    "error":       _twilio_error,
                    "recipient":   _twilio_recipient,
                })
                try:
                    if SessionLocal is not None:
                        with SessionLocal() as _log:
                            _log.add(DeliveryLog(
                                cbm_id        = cbm_id,
                                user_id       = user_id,
                                channel       = _twilio_channel,
                                success       = _twilio_success,
                                error_message = _twilio_error,
                                created_on    = datetime.utcnow(),
                            ))
                            _log.commit()
                except Exception:
                    pass

            test_email = os.environ.get("OUTBOUND_TEST_EMAIL", "")
            if test_email:
                print(f"[OutboundDeliveryService] TEST OVERRIDE email={test_email!r}")
                email = test_email

            email_host     = os.environ.get("EMAIL_HOST", "")
            email_from     = os.environ.get("EMAIL_FROM", "")
            email_password = os.environ.get("EMAIL_PASSWORD", "")

            if email_host and email_from and email_password and email:
                _email_success   = False
                _email_error     = None
                _email_recipient = None
                try:
                    import smtplib
                    from email.mime.text import MIMEText
                    msg = MIMEText(message)
                    msg["Subject"] = "Message from Colaberry AI"
                    msg["From"]    = email_from
                    msg["To"]      = email
                    _email_recipient = email
                    with smtplib.SMTP_SSL(email_host) as server:
                        server.login(email_from, email_password)
                        server.sendmail(email_from, email, msg.as_string())
                    print(f"[OutboundDeliveryService][EMAIL SENT] to={email!r}")
                    _email_success = True
                except Exception as e:
                    _email_error = str(e)
                    print(f"[OutboundDeliveryService][EMAIL ERROR] {e}")
                results.append({
                    "success":     _email_success,
                    "channel":     "email",
                    "provider":    "smtp",
                    "provider_id": None,
                    "error":       _email_error,
                    "recipient":   _email_recipient,
                })
                try:
                    if SessionLocal is not None:
                        with SessionLocal() as _log:
                            _log.add(DeliveryLog(
                                cbm_id        = cbm_id,
                                user_id       = user_id,
                                channel       = "email",
                                success       = _email_success,
                                error_message = _email_error,
                                created_on    = datetime.utcnow(),
                            ))
                            _log.commit()
                except Exception:
                    pass

            # Integration point — _send_mandrill_email():
            # When the Mandrill adapter is activated, add a block here:
            #   mandrill_api_key = os.environ.get("MANDRILL_API_KEY", "")
            #   mandrill_from    = os.environ.get("MANDRILL_FROM_EMAIL", "")
            #   if mandrill_api_key and mandrill_from and email:
            #       results.append(self._send_mandrill_email(email=email, message=message))

            # Integration point — _send_twilio_voice():
            # When voice is activated, add a block here gated on TWILIO_ACCOUNT_SID and phone:
            #   if account_sid and auth_token and phone:
            #       results.append(self._send_twilio_voice(phone=phone, message=message))

            return results
        except Exception:
            return results

    # -------------------------------------------------------------------------
    # Provider adapter stubs
    #
    # Not yet wired into send_text(). Each returns a DeliveryResult dict that
    # matches the delivery contract exactly. When a provider is activated, the
    # stub body is replaced with the real API call — the signature and return
    # shape must not change.
    # -------------------------------------------------------------------------

    def _send_twilio_sms(self, phone: str, message: str) -> dict:
        """Adapter stub — Twilio SMS.

        Real implementation calls the Twilio REST API to send an SMS from
        TWILIO_FROM_NUMBER to ``phone``. Returns the message SID as provider_id.
        """
        return {
            "success":     False,
            "channel":     "sms",
            "provider":    "twilio",
            "provider_id": None,
            "error":       "not_configured",
            "recipient":   phone,
        }

    def _send_twilio_whatsapp(self, phone: str, message: str) -> dict:
        """Adapter stub — Twilio WhatsApp.

        Real implementation calls the Twilio REST API using the whatsapp: address
        prefix. Sender is the Twilio sandbox number (+14155238886) until a
        production WhatsApp sender is provisioned.
        """
        return {
            "success":     False,
            "channel":     "whatsapp",
            "provider":    "twilio",
            "provider_id": None,
            "error":       "not_configured",
            "recipient":   f"whatsapp:{phone}",
        }

    def _send_twilio_voice(self, phone: str, message: str) -> dict:
        """Adapter stub — Twilio Voice (text-to-speech).

        Real implementation uses the Twilio Calls API with TwiML <Say> to read
        ``message`` aloud to ``phone``. Returns the call SID as provider_id.
        """
        return {
            "success":     False,
            "channel":     "voice",
            "provider":    "twilio",
            "provider_id": None,
            "error":       "not_configured",
            "recipient":   phone,
        }

    def _send_mandrill_email(self, email: str, message: str) -> dict:
        """Adapter stub — Mandrill (Mailchimp Transactional) email.

        Real implementation posts to the Mandrill /messages/send API using
        MANDRILL_API_KEY. Returns the Mandrill message _id as provider_id.
        """
        return {
            "success":     False,
            "channel":     "mandrill_email",
            "provider":    "mandrill",
            "provider_id": None,
            "error":       "not_configured",
            "recipient":   email,
        }
