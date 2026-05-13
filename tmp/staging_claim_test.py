"""
Staging claim test — OUTPUT INSERTED.CBM_ID on real SQL Server.

Usage:
    MSSQL_DATABASE_URL="mssql+pyodbc://..." python tmp/staging_claim_test.py

What this does:
1. Inserts a minimal TriggeredUser row (Completed=0) directly into SQL Server.
2. Calls process_trigger() for that cbm_id with send_text() patched to a no-op.
   - First call must claim the row and return cbm_id.
3. Calls process_trigger() again for the same cbm_id.
   - Second call must return already_claimed without touching send_text.
4. Asserts both outcomes, prints a pass/fail report, and deletes the test row.

The test row is cleaned up in a finally block — safe to re-run.
"""

import os
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

# ── guard: refuse to run without a real SQL Server URL ────────────────────────
if not os.environ.get("MSSQL_DATABASE_URL"):
    print("FAIL  MSSQL_DATABASE_URL is not set.")
    print("      Export it before running this script.")
    sys.exit(1)

# ── project root on path ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import SessionLocal, MSSQL_CONFIGURED
from services.models import TriggeredUser
from services.mentor_message_service import MentorMessageService

if not MSSQL_CONFIGURED:
    print("FAIL  MSSQL_CONFIGURED is False even though MSSQL_DATABASE_URL is set.")
    print("      Check config/database.py.")
    sys.exit(1)

# ── helpers ───────────────────────────────────────────────────────────────────

def insert_test_row() -> int:
    with SessionLocal() as session:
        row = TriggeredUser(
            CB_ID        = None,
            UserID       = None,
            TriggerType  = "staging_claim_test",
            TriggerLevel = "Low",
            KPI          = None,
            Severity     = None,
            InsertDate   = datetime.utcnow(),
            Completed    = 0,
            AgentID      = None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.CBM_ID


def delete_test_row(cbm_id: int) -> None:
    with SessionLocal() as session:
        row = session.get(TriggeredUser, cbm_id)
        if row is not None:
            session.delete(row)
            session.commit()


def read_completed(cbm_id: int) -> int | None:
    with SessionLocal() as session:
        row = session.get(TriggeredUser, cbm_id)
        return row.Completed if row is not None else None


# ── test ──────────────────────────────────────────────────────────────────────

cbm_id = insert_test_row()
print(f"\nINFO  Inserted test row  cbm_id={cbm_id}  Completed=0")

passed = True

try:
    fake_delivery = MagicMock(return_value=[])   # no real sends

    with patch("services.mentor_message_service.OutboundDeliveryService.send_text",
               fake_delivery):

        svc = MentorMessageService()

        # ── first call ────────────────────────────────────────────────────────
        first = svc.process_trigger(cbm_id)
        completed_after_first = read_completed(cbm_id)

        print(f"\n--- First call ---")
        print(f"  result          : {first}")
        print(f"  Completed in DB : {completed_after_first}")
        print(f"  send_text calls : {fake_delivery.call_count}")

        if first.get("cbm_id") != cbm_id:
            print(f"FAIL  Expected cbm_id={cbm_id} in result, got: {first}")
            passed = False
        else:
            print(f"PASS  First call returned cbm_id={cbm_id}")

        if completed_after_first != 1:
            print(f"FAIL  Expected Completed=1 after first call, got {completed_after_first}")
            passed = False
        else:
            print(f"PASS  Completed=1 confirmed in SQL Server via OUTPUT INSERTED")

        if fake_delivery.call_count != 1:
            print(f"FAIL  send_text called {fake_delivery.call_count} times (expected 1)")
            passed = False
        else:
            print(f"PASS  send_text called exactly once")

        # ── second call ───────────────────────────────────────────────────────
        second = svc.process_trigger(cbm_id)

        print(f"\n--- Second call ---")
        print(f"  result          : {second}")
        print(f"  send_text calls : {fake_delivery.call_count}")

        if second != {"sent": False, "reason": "already_claimed"}:
            print(f"FAIL  Expected already_claimed, got: {second}")
            passed = False
        else:
            print(f"PASS  Second call returned already_claimed")

        if fake_delivery.call_count != 1:
            print(f"FAIL  send_text was called again on second call (duplicate send risk active)")
            passed = False
        else:
            print(f"PASS  send_text call count unchanged — no duplicate send")

finally:
    delete_test_row(cbm_id)
    print(f"\nINFO  Test row deleted  cbm_id={cbm_id}")

print(f"\n{'ALL CHECKS PASSED' if passed else 'ONE OR MORE CHECKS FAILED'}")
sys.exit(0 if passed else 1)
