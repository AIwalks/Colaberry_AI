"""Standalone worker — processes all pending TriggeredUser rows.

Run directly:
    python -m services.worker.trigger_worker

Or import and call from a scheduler or management script:
    from services.worker.trigger_worker import process_pending_triggers
    processed = process_pending_triggers()
"""

from sqlalchemy import select

from config.database import SessionLocal, MSSQL_CONFIGURED
from services.mentor_message_service import MentorMessageService
from services.models import TriggeredUser


def process_pending_triggers() -> int:
    """Process every TriggeredUser row where Completed == 0.

    Each row is passed to MentorMessageService.process_trigger(), which
    writes the audit log, the engagement event, and flips Completed = 1
    in its own committed session.

    Returns
    -------
    int — number of rows handed to process_trigger() in this run.
          Returns 0 immediately if SessionLocal is not configured.
    """
    if not MSSQL_CONFIGURED:
        return 0

    # Load all pending CBM_IDs before closing the session.
    # Extracting plain ints avoids DetachedInstanceError after session close.
    with SessionLocal() as session:
        rows = session.execute(
            select(TriggeredUser).where(TriggeredUser.Completed == 0)
        ).scalars().all()
        cbm_ids = [row.CBM_ID for row in rows]

    count = 0
    for cbm_id in cbm_ids:
        try:
            MentorMessageService().process_trigger(cbm_id)
        except Exception as e:
            print(f"[ERROR] Failed processing trigger {cbm_id}: {e}")
            continue
        count += 1

    return count


if __name__ == "__main__":
    processed = process_pending_triggers()
    print(f"Processed {processed} pending trigger(s).")
