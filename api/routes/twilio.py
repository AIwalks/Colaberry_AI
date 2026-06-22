"""Twilio inbound webhook endpoint.

Receives inbound WhatsApp messages posted by Twilio.
Resolves the sender phone number to a TriggerData.UserID, then writes
an EngagementEvent row so the response matching worker can link the reply
to its originating nudge via MessageSid (thread_id).

Returns an empty TwiML <Response/> to acknowledge receipt without auto-replying.
Authentication is handled per-request by validate_twilio_signature — this router
is intentionally NOT wrapped with require_api_key.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form
from fastapi.responses import Response

from config.database import MSSQL_CONFIGURED, SessionLocal
from config.twilio_auth import validate_twilio_signature
from services.engagement_tracker_service import EngagementTrackerService
from services.models import TriggerData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio", tags=["twilio"])

_TWIML_EMPTY = '<?xml version="1.0"?><Response/>'


# ---------------------------------------------------------------------------
# Optional DB dependency — same pattern as api/routes/sentinel.py
# ---------------------------------------------------------------------------

def _get_db_optional():
    if not MSSQL_CONFIGURED or SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phone resolution
# ---------------------------------------------------------------------------

def _resolve_phone(phone: str, db) -> int | None:
    """Return TriggerData.UserID for the given phone number, or None if not found.

    Strips the 'whatsapp:' prefix Twilio prepends to WhatsApp sender numbers.
    Returns None if db is None (MSSQL not configured) or the number is unknown.
    """
    if db is None:
        return None
    normalized = phone.removeprefix("whatsapp:").strip()
    row = db.query(TriggerData).filter(TriggerData.PhoneNumber == normalized).first()
    return int(row.UserID) if row else None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/inbound",
    dependencies=[Depends(validate_twilio_signature)],
    response_class=Response,
    summary="Receive inbound WhatsApp message from Twilio",
)
async def twilio_inbound(
    From: str = Form(...),
    Body: str = Form(default=""),
    MessageSid: str = Form(...),
    db=Depends(_get_db_optional),
) -> Response:
    """Handle a Twilio inbound WhatsApp webhook POST.

    Fields per Twilio spec:
      From       — sender number, e.g. "whatsapp:+15005550006"
      Body       — message text (may be empty for media-only messages)
      MessageSid — Twilio message SID used as thread_id for response matching
    """
    user_id = _resolve_phone(From, db)

    if MSSQL_CONFIGURED:
        EngagementTrackerService().log_event(
            user_id=user_id,
            event_type="incoming_message",
            channel="whatsapp",
            message=Body,
            agent_name="TwilioWebhook",
            thread_id=f"wa:{user_id}" if user_id is not None else None,
        )
    else:
        logger.warning(
            "TwilioWebhook: MSSQL not configured — EngagementEvent skipped "
            "(From=%s MessageSid=%s)",
            From,
            MessageSid,
        )

    return Response(content=_TWIML_EMPTY, media_type="text/xml")
