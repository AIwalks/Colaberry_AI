import os

import pytest
from config.database import MSSQL_CONFIGURED, SessionLocal
from services.worker.trigger_worker import process_pending_triggers
from services.models import TriggeredUser, EngagementEvent

pytestmark = pytest.mark.skipif(
    not MSSQL_CONFIGURED, reason="MSSQL_DATABASE_URL not set"
)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_worker_runs(db_session):

    test_row = TriggeredUser(
        UserID=999999,
        TriggerType="TEST",
        TriggerLevel="TEST",
        KPI="TEST",
        Severity=1,
        Completed=0
    )

    db_session.add(test_row)
    db_session.commit()

    process_pending_triggers()

    updated = db_session.query(TriggeredUser).filter_by(UserID=999999).first()

    assert updated is not None
    assert updated.Completed in (0, 1)

    event = db_session.query(EngagementEvent).order_by(EngagementEvent.id.desc()).first()

    assert event is not None
