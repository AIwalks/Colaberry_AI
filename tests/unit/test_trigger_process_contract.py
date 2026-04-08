"""Contract test for POST /ai/trigger/process happy path."""

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from config.database import SessionLocal
from services.models import TriggerRule, TriggeredUser
from services.trigger_processing_service import DbTriggerProcessingService, TriggerProcessingService

client = TestClient(app)


def test_get_trigger_processing_service_routes_correctly_by_session():
    """get_trigger_processing_service() must return DbTriggerProcessingService
    when SessionLocal is available, and TriggerProcessingService (stub) when it is None.

    Covers both environment paths:
      a) SessionLocal is None  → no DB available → stub service
      b) SessionLocal is set   → DB available (SQLite or MSSQL) → DB-backed service
    """
    original_session = main_module.SessionLocal
    try:
        # a) Simulate no database session — stub service expected
        main_module.SessionLocal = None
        svc = main_module.get_trigger_processing_service()
        assert isinstance(svc, TriggerProcessingService), (
            "Expected TriggerProcessingService (stub) when SessionLocal is None"
        )

        # b) Restore session — DB-backed service expected
        main_module.SessionLocal = original_session
        svc = main_module.get_trigger_processing_service()
        assert isinstance(svc, DbTriggerProcessingService), (
            "Expected DbTriggerProcessingService when SessionLocal is available"
        )
    finally:
        main_module.SessionLocal = original_session


def test_post_trigger_process_inserts_triggered_user_row_in_local_db():
    """POST /ai/trigger/process must insert a TriggeredUser row into the local DB.

    Uses a seeded TriggerRule so DbTriggerProcessingService finds a matching rule.
    Verifies key fields on the inserted row, then cleans up both seeded rows.
    Runs against local SQLite — no MSSQL required.
    """
    _CB_ID       = 99901
    _TRIGGER_TYPE = "TEST_LOCAL_INSERTION"
    _STUDENT_ID  = "999999"

    with SessionLocal() as session:
        # Clean any leftover rows from a prior failed run
        session.query(TriggeredUser).filter_by(TriggerType=_TRIGGER_TYPE).delete()
        session.query(TriggerRule).filter_by(CB_ID=_CB_ID).delete()
        session.commit()

        # Seed a minimal TriggerRule so the service finds a match
        rule = TriggerRule(
            CB_ID       = _CB_ID,
            TriggerType = _TRIGGER_TYPE,
            KPI         = None,
            Severity    = 1,
            TriggerLow  = None,
            TriggerHigh = None,
            AgentID     = None,
        )
        session.add(rule)
        session.commit()

    try:
        resp = client.post("/ai/trigger/process", json={
            "trigger_type": _TRIGGER_TYPE,
            "student_id":   _STUDENT_ID,
            "event_id":     "TEST-EVT-LOCAL-001",
            "timestamp":    "2026-04-08T09:00:00Z",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True, f"Expected accepted=True, got: {data}"

        # Verify the TriggeredUser row was inserted with correct mapped fields
        with SessionLocal() as session:
            row = (
                session.query(TriggeredUser)
                .filter_by(TriggerType=_TRIGGER_TYPE)
                .order_by(TriggeredUser.CBM_ID.desc())
                .first()
            )
            assert row is not None,              "TriggeredUser row was not inserted"
            assert row.TriggerType == _TRIGGER_TYPE
            assert row.CB_ID       == _CB_ID
            assert row.Completed   == 0,         "New trigger must start as Completed=0"
            assert row.InsertDate  is not None,  "InsertDate must be set on insert"

    finally:
        # Always remove seeded rows regardless of assertion outcome
        with SessionLocal() as session:
            session.query(TriggeredUser).filter_by(TriggerType=_TRIGGER_TYPE).delete()
            session.query(TriggerRule).filter_by(CB_ID=_CB_ID).delete()
            session.commit()


def test_trigger_process_happy_path_returns_expected_shape_and_mapping():
    """POST /ai/trigger/process happy path — real DB-backed service, real rule lookup.

    Previously this test relied on the TriggerProcessingService stub which used an
    in-memory dict (no DB). Now that DbTriggerProcessingService is always used, a
    matching TriggerRule must exist in the DB for the trigger to be accepted.

    Seeds a 'nudge_needed' rule with no KPI thresholds (TriggerEvaluator returns
    'Unknown' level), verifies the full response shape and mapped values, then
    cleans up. actions_planned comes from _ACTION_MAP[('nudge_needed', 'Unknown')].
    """
    _CB_ID        = 99902
    _TRIGGER_TYPE = "nudge_needed"

    with SessionLocal() as session:
        session.query(TriggerRule).filter_by(CB_ID=_CB_ID).delete()
        session.commit()
        session.add(TriggerRule(
            CB_ID       = _CB_ID,
            TriggerType = _TRIGGER_TYPE,
            KPI         = None,
            Severity    = 1,
            TriggerLow  = None,
            TriggerHigh = None,
            AgentID     = None,
        ))
        session.commit()

    try:
        resp = client.post("/ai/trigger/process", json={
            "trigger_type": _TRIGGER_TYPE,
            "student_id":   "S1",
            "event_id":     "E1",
            "timestamp":    "2026-02-10T00:00:00Z",
            "metadata":     {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"event_id", "accepted", "actions_planned", "notes"}
        assert data["event_id"]        == "E1"
        assert data["accepted"]        is True
        assert data["actions_planned"] == ["queue_nudge_message"]
        assert isinstance(data["notes"], str) and len(data["notes"]) > 0
    finally:
        with SessionLocal() as session:
            session.query(TriggeredUser).filter_by(TriggerType=_TRIGGER_TYPE).delete()
            session.query(TriggerRule).filter_by(CB_ID=_CB_ID).delete()
            session.commit()
