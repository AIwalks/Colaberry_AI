"""Outbound delivery service — stub implementation.

Real delivery (Twilio SMS, email, etc.) will replace the print stub
when channel credentials are available. The interface is intentionally
kept stable so callers do not need to change when the real implementation
is wired in.
"""

import os
from config.database import SessionLocal
from services.models import TriggerData


class OutboundDeliveryService:

    def send_text(self, user_id: int, message: str) -> bool:
        """Send a text message to a student.

        Parameters
        ----------
        user_id : int
            The UserID from AI_ChatBot_TriggerData.
        message : str
            The message text to deliver.

        Returns
        -------
        bool — True if delivery succeeded (or was attempted), False on error.
        """
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

            if account_sid and auth_token and from_number and phone:
                try:
                    from twilio.rest import Client
                    use_whatsapp = os.environ.get("OUTBOUND_USE_WHATSAPP") == "1"
                    if use_whatsapp:
                        from_addr = "whatsapp:+14155238886"
                        to_addr   = f"whatsapp:{phone}"
                    else:
                        from_addr = from_number
                        to_addr   = phone
                    msg = Client(account_sid, auth_token).messages.create(
                        body=message,
                        from_=from_addr,
                        to=to_addr,
                    )
                    print(f"[OutboundDeliveryService][TWILIO SENT] sid={msg.sid}")
                except Exception as e:
                    print(f"[OutboundDeliveryService][TWILIO ERROR] {e}")

            return True
        except Exception:
            return False
