"""Unit tests for services/worker/trigger_worker.py — process_pending_triggers()."""

from unittest.mock import MagicMock, patch, call


def test_worker_continues_after_one_trigger_failure():
    """If one cbm_id raises, the worker must continue processing the rest.

    Proves loop isolation: a single failure must not abort the batch.
    Returned count must reflect only successfully processed triggers.
    """
    cbm_ids = [101, 102, 103]

    def fake_process_trigger(cbm_id):
        if cbm_id == 102:
            raise Exception("simulated failure")

    fake_session = MagicMock()
    fake_triggered_users = [MagicMock(CBM_ID=cid) for cid in cbm_ids]
    fake_session.__enter__ = MagicMock(return_value=fake_session)
    fake_session.__exit__ = MagicMock(return_value=False)
    fake_session.execute.return_value.scalars.return_value.all.return_value = (
        fake_triggered_users
    )

    with patch(
        "services.worker.trigger_worker.MSSQL_CONFIGURED", True
    ), patch(
        "services.worker.trigger_worker.SessionLocal", return_value=fake_session
    ), patch(
        "services.worker.trigger_worker.MentorMessageService"
    ) as MockService:
        MockService.return_value.process_trigger.side_effect = fake_process_trigger

        from services.worker.trigger_worker import process_pending_triggers

        count = process_pending_triggers()

    # 101 and 103 succeed; 102 raises — count must be 2, not 3
    assert count == 2

    # All three cbm_ids must have been attempted
    attempted = [
        c.args[0]
        for c in MockService.return_value.process_trigger.call_args_list
    ]
    assert attempted == [101, 102, 103]
