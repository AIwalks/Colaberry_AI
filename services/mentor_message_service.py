"""Orchestrates mentor message flows — inbound acknowledgement and outbound trigger dispatch."""

from datetime import datetime
from config.database import SessionLocal
from services.audit_log_service import AuditLogService
from services.engagement_tracker_service import EngagementTrackerService
from services.outbound_delivery_service import OutboundDeliveryService
from services.models import TriggeredUser


class MentorMessageService:

    # ------------------------------------------------------------------
    # Inbound path — called by POST /ai/mentor/message
    # ------------------------------------------------------------------

    def handle(self, *, body, request_id: str, status_fetcher) -> dict:
        result = {
            "request_id": request_id,
            "received": {
                "student_id": body.student_id,
                "channel": body.channel if isinstance(body.channel, str) else body.channel.value,
                "message": body.message,
            },
            "student_status": status_fetcher.fetch_status(body.student_id),
            "delivery": {
                "channel": body.channel if isinstance(body.channel, str) else body.channel.value,
                "constraints": {
                    "max_length": 1000,
                },
            },
            "response_message": {
                "text": "Your message has been received and logged. A mentor will follow up shortly.",
            },
            "engagement_log": {
                "logged": True,
                "event_type": "incoming_message",
            },
        }

        try:
            AuditLogService().log_event(
                phone_number=None,
                entry_type="incoming_message",
                input_message=body.message,
                output_message=result["response_message"]["text"],
                cbm_id=None,
                email=None,
                channel=body.channel if isinstance(body.channel, str) else body.channel.value,
                processing_time_seconds=None,
            )
        except Exception:
            pass

        try:
            EngagementTrackerService().log_event(
                user_id=None,
                event_type="incoming_message",
                channel=body.channel if isinstance(body.channel, str) else body.channel.value,
                message=body.message,
                agent_name="MentorMessageService",
                trigger_id=None,
            )
        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Outbound path — called after a trigger is accepted
    # ------------------------------------------------------------------

    def process_trigger(self, cbm_id: int) -> dict:
        """Read a TriggeredUser row, log the outbound action, mark it complete.

        Returns
        -------
        {"sent": True,  "cbm_id": cbm_id}      — row found and processed
        {"sent": False, "reason": "not_found"}  — no row for that CBM_ID
        {"sent": False, "reason": "no_db"}      — SessionLocal not configured
        """
        if SessionLocal is None:
            return {"sent": False, "reason": "no_db"}

        with SessionLocal() as session:
            triggered: TriggeredUser | None = session.get(TriggeredUser, cbm_id)

            if triggered is None:
                return {"sent": False, "reason": "not_found"}

            message_text = (
                f"Trigger {triggered.TriggerType} level {triggered.TriggerLevel}"
            )

            # Non-blocking — failure must not prevent completion
            try:
                AuditLogService().log_event(
                    phone_number            = None,
                    entry_type              = "outbound_trigger",
                    input_message           = None,
                    output_message          = message_text,
                    cbm_id                  = cbm_id,
                    email                   = None,
                    channel                 = None,
                    processing_time_seconds = None,
                )
            except Exception:
                pass

            try:
                EngagementTrackerService().log_event(
                    user_id    = triggered.UserID,
                    event_type = "trigger_dispatched",
                    channel    = None,
                    message    = message_text,
                    agent_name = "MentorMessageService",
                    trigger_id = cbm_id,
                )
            except Exception:
                pass

            OutboundDeliveryService().send_text(
                user_id=triggered.UserID,
                message=message_text,
            )

            triggered.Completed = 1
            triggered.CompletedDate = datetime.utcnow()
            session.commit()

        return {"sent": True, "cbm_id": cbm_id}
