"""Append-only engagement event writer for AI_ChatBot_EngagementEvents."""

from datetime import datetime

from config.database import SessionLocal
from services.models import EngagementEvent


class EngagementTrackerService:
    """Inserts a single engagement event row and returns its auto-generated id.

    This service performs no routing, dispatch, or message generation.
    It is an append-only DB writer; callers supply all field values.

    Run the Alembic migration before using this service against a live DB:

        alembic upgrade head
    """

    def log_event(
        self,
        *,
        user_id:    int | None,
        event_type: str,
        channel:    str | None,
        message:    str | None,
        agent_name: str | None,
        trigger_id: int | None = None,
    ) -> int:
        """Insert one engagement event and return its primary key.

        Parameters
        ----------
        user_id     : Reference to AI_ChatBot_TriggerData.UserID; None for
                      system-level or anonymous events.
        event_type  : Required classifier, e.g. "nudge_sent", "trigger_fired".
        channel     : Delivery channel: "whatsapp", "sms", "email", "web", etc.
        message     : Human-readable description or the actual message text.
        agent_name  : Name of the agent that produced the event.
        trigger_id  : Reference to AI_ChatBot_TriggeredUsers.CBM_ID; None when
                      the event was not produced by a rule evaluation.

        Returns
        -------
        int — the auto-incremented id of the inserted row.

        Raises
        ------
        RuntimeError — if MSSQL_DATABASE_URL is not configured (SessionLocal is None).
        """
        if SessionLocal is None:
            raise RuntimeError(
                "EngagementTrackerService requires MSSQL_DATABASE_URL to be set."
            )

        event = EngagementEvent(
            user_id    = user_id,
            event_type = event_type,
            channel    = channel,
            message    = message,
            agent_name = agent_name,
            trigger_id = trigger_id,
            created_at = datetime.utcnow(),
        )

        with SessionLocal() as session:
            session.add(event)
            session.commit()
            session.refresh(event)
            return event.id
