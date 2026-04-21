"""Orchestrates mentor message flows — inbound acknowledgement and outbound trigger dispatch."""

from datetime import datetime
from config.database import SessionLocal, MSSQL_CONFIGURED
from services.audit_log_service import AuditLogService
from services.engagement_tracker_service import EngagementTrackerService
from services.outbound_delivery_service import OutboundDeliveryService
from services.models import TriggeredUser, TriggerRule, TriggerData
from services.trigger_processing_service import TriggerEvaluator


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
        if not MSSQL_CONFIGURED:
            return {"sent": False, "reason": "no_db"}

        with SessionLocal() as session:
            triggered: TriggeredUser | None = session.get(TriggeredUser, cbm_id)

            if triggered is None:
                return {"sent": False, "reason": "not_found"}

            _fallback = f"Trigger {triggered.TriggerType} level {triggered.TriggerLevel}"
            try:
                rule    = session.get(TriggerRule, triggered.CB_ID) if triggered.CB_ID is not None else None
                student = session.get(TriggerData, triggered.UserID) if triggered.UserID is not None else None
                eval_result = TriggerEvaluator().evaluate(rule, student, event_id=str(cbm_id)) if rule is not None else {}
                message_text = eval_result.get("message_text") or _fallback
            except Exception:
                message_text = _fallback

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

            # Commit before delivery — ensures Completed=1 is durable before
            # any send attempt. If commit raises, send_text is never called and
            # the trigger stays Completed=0 for a clean retry next poll cycle.
            user_id = triggered.UserID
            triggered.Completed = 1
            triggered.CompletedDate = datetime.utcnow()
            session.commit()

        # Send AFTER session is closed and commit is durable.
        # If send_text fails, Completed=1 is already in the DB —
        # the worker will not retry, preventing a duplicate send.
        try:
            delivery_results = OutboundDeliveryService().send_text(
                user_id=user_id,
                message=message_text,
                cbm_id=cbm_id,
            )
        except Exception as e:
            print(f"[WARNING] Delivery failed for cbm_id={cbm_id}: {e}")
            try:
                with SessionLocal() as session:
                    row: TriggeredUser | None = session.get(TriggeredUser, cbm_id)
                    if row is not None:
                        row.DeliverySucceeded = False
                        session.commit()
            except Exception as wb_err:
                print(f"[WARNING] Could not write DeliverySucceeded=False for cbm_id={cbm_id}: {wb_err}")
                try:
                    with SessionLocal() as retry_session:
                        retry_row: TriggeredUser | None = retry_session.get(TriggeredUser, cbm_id)
                        if retry_row is not None:
                            retry_row.DeliverySucceeded = False
                            retry_session.commit()
                except Exception as retry_err:
                    print(f"[CRITICAL] DeliverySucceeded could not be persisted for cbm_id={cbm_id}: {retry_err}")
            return {"sent": False, "reason": "delivery_failed", "cbm_id": cbm_id}

        sent = any(r.get("success") for r in delivery_results)

        # Write delivery outcome back to the trigger record.
        # This is a best-effort update — failure must not affect the caller's result.
        # DeliverySucceeded=True  → at least one channel succeeded
        # DeliverySucceeded=False → delivery was attempted but all channels failed
        # DeliverySucceeded=None  → left only when delivery_results is empty (no attempt made)
        delivery_succeeded: bool | None = sent if delivery_results else None
        try:
            with SessionLocal() as session:
                row: TriggeredUser | None = session.get(TriggeredUser, cbm_id)
                if row is not None:
                    row.DeliverySucceeded = delivery_succeeded
                    session.commit()
        except Exception as e:
            print(f"[WARNING] Could not write DeliverySucceeded for cbm_id={cbm_id}: {e}")
            try:
                with SessionLocal() as retry_session:
                    retry_row: TriggeredUser | None = retry_session.get(TriggeredUser, cbm_id)
                    if retry_row is not None:
                        retry_row.DeliverySucceeded = delivery_succeeded
                        retry_session.commit()
            except Exception as retry_err:
                print(f"[CRITICAL] DeliverySucceeded could not be persisted for cbm_id={cbm_id}: {retry_err}")

        return {"sent": sent, "cbm_id": cbm_id, "delivery_results": delivery_results}
