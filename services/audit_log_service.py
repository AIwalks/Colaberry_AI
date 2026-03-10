"""Append-only audit log writer for AI_ChatBot_AuditLog."""

from datetime import datetime

from config.database import SessionLocal
from services.models import ChatBotAuditLog


class AuditLogService:
    """Writes a single entry to AI_ChatBot_AuditLog and returns its entry_id.

    Callers are responsible for supplying all field values; this service
    does no message generation or routing logic.
    """

    def log_event(
        self,
        *,
        phone_number: str | None,
        entry_type: str,
        input_message: str | None,
        output_message: str | None,
        cbm_id: int | None,
        email: str | None,
        channel: str | None,
        processing_time_seconds: float | None,
    ) -> int:
        """Insert one audit log row and return its auto-generated entry_id.

        Parameters
        ----------
        phone_number             : Student or contact phone number.
        entry_type               : e.g. "incoming_message", "outbound_response".
        input_message            : Raw inbound text (may be None for outbound-only entries).
        output_message           : Generated or sent text (may be None for inbound-only).
        cbm_id                   : FK to AI_ChatBot_TriggeredUsers.CBM_ID; None for unsolicited.
        email                    : Contact email address.
        channel                  : Delivery channel, e.g. "whatsapp", "sms", "email".
        processing_time_seconds  : Wall-clock seconds spent generating the response.

        Returns
        -------
        int — the auto-incremented entry_id of the inserted row.

        Raises
        ------
        RuntimeError — if MSSQL_DATABASE_URL is not configured (SessionLocal is None).
        """
        if SessionLocal is None:
            raise RuntimeError(
                "AuditLogService requires MSSQL_DATABASE_URL to be set."
            )

        entry = ChatBotAuditLog(
            phone_number            = phone_number,
            entry_type              = entry_type,
            input_message           = input_message,
            output_message          = output_message,
            created_at              = datetime.utcnow(),
            CBM_ID                  = cbm_id,
            Email                   = email,
            Channel                 = channel,
            ProcessingTimeSeconds   = processing_time_seconds,
        )

        with SessionLocal() as session:
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry.entry_id
