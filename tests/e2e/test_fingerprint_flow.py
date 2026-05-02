"""End-to-end flow test for POST /fingerprints/evaluate.

Uses the real route, real FingerprintService, and real FingerprintEvaluator.
The DB session is replaced with a lightweight fake that captures writes and
simulates a successful commit without touching any external service.

No mocks on the service or evaluator layer — this test exercises the full
in-process call chain:

    TestClient → route → FingerprintService → FingerprintEvaluator → fake DB
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from config.database import get_db


# ---------------------------------------------------------------------------
# Fake DB session
#
# Simulates a SQLAlchemy session without a real connection.
# refresh() sets id=1 on the object so FingerprintService.evaluate_and_store
# can return a complete record after db.commit().
# ---------------------------------------------------------------------------

class FakeSession:
    """Minimal SQLAlchemy session stand-in for e2e flow tests."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        obj.id = 1

    def close(self):
        pass


def fake_db():
    session = FakeSession()
    try:
        yield session
    finally:
        session.close()


client = TestClient(app, headers={"X-Api-Key": "test-key"})


@pytest.fixture(autouse=True)
def set_db_override():
    app.dependency_overrides[get_db] = fake_db
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

VALID_BODY = {
    "entity_type": "student",
    "entity_id": "student_42",
    "pattern_name": "disengagement",
    "thresholds": {"logins": 5, "sessions": 3},
    "metrics": {"logins": 10, "sessions": 5},
}

EXPECTED_KEYS = {
    "id",
    "entity_type",
    "entity_id",
    "pattern_name",
    "score",
    "risk_level",
    "details_json",
}

VALID_RISK_LEVELS = {"low", "medium", "high"}


# ---------------------------------------------------------------------------
# POST /fingerprints/evaluate returns 200
# ---------------------------------------------------------------------------

def test_evaluate_returns_200():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert resp.status_code == 200


def test_evaluate_returns_json_content_type():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert "application/json" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Response has valid schema
# ---------------------------------------------------------------------------

def test_response_has_all_expected_keys():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert set(resp.json().keys()) == EXPECTED_KEYS


def test_response_id_is_integer():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert isinstance(resp.json()["id"], int)


def test_response_entity_type_matches_request():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert resp.json()["entity_type"] == VALID_BODY["entity_type"]


def test_response_entity_id_matches_request():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert resp.json()["entity_id"] == VALID_BODY["entity_id"]


def test_response_pattern_name_matches_request():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert resp.json()["pattern_name"] == VALID_BODY["pattern_name"]


# ---------------------------------------------------------------------------
# Score between 0.0 and 1.0 — computed by real FingerprintEvaluator
# ---------------------------------------------------------------------------

def test_score_is_float():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert isinstance(resp.json()["score"], float)


def test_score_is_between_0_and_1():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    score = resp.json()["score"]
    assert 0.0 <= score <= 1.0


def test_all_thresholds_met_score_is_1():
    """Metrics exceed all thresholds — real evaluator must return score=1.0."""
    body = {
        "entity_type": "student",
        "entity_id": "s1",
        "pattern_name": "active",
        "thresholds": {"logins": 5},
        "metrics": {"logins": 10},
    }
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["score"] == 1.0


def test_no_thresholds_met_score_is_0():
    """Metrics all below thresholds — real evaluator must return score=0.0."""
    body = {
        "entity_type": "student",
        "entity_id": "s2",
        "pattern_name": "inactive",
        "thresholds": {"logins": 100},
        "metrics": {"logins": 1},
    }
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["score"] == 0.0


# ---------------------------------------------------------------------------
# risk_level is one of the valid values — assigned by real evaluator
# ---------------------------------------------------------------------------

def test_risk_level_is_valid():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert resp.json()["risk_level"] in VALID_RISK_LEVELS


def test_all_thresholds_met_risk_is_high():
    """score=1.0 → evaluator must assign risk_level='high'."""
    body = {
        "entity_type": "student",
        "entity_id": "s3",
        "pattern_name": "active",
        "thresholds": {"logins": 5},
        "metrics": {"logins": 10},
    }
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["risk_level"] == "high"


def test_no_thresholds_met_risk_is_low():
    """score=0.0 → evaluator must assign risk_level='low'."""
    body = {
        "entity_type": "student",
        "entity_id": "s4",
        "pattern_name": "inactive",
        "thresholds": {"logins": 100},
        "metrics": {"logins": 1},
    }
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["risk_level"] == "low"


# ---------------------------------------------------------------------------
# Empty thresholds — valid edge case, must return score=0.0 and risk=low
# ---------------------------------------------------------------------------

def test_empty_thresholds_returns_200():
    body = {**VALID_BODY, "thresholds": {}}
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.status_code == 200


def test_empty_thresholds_score_is_zero():
    """Real evaluator: no thresholds → score = 0.0."""
    body = {**VALID_BODY, "thresholds": {}}
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["score"] == 0.0


def test_empty_thresholds_risk_is_low():
    """Real evaluator: score=0.0 → risk_level='low'."""
    body = {**VALID_BODY, "thresholds": {}}
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["risk_level"] == "low"


def test_empty_thresholds_details_json_is_valid():
    body = {**VALID_BODY, "thresholds": {}}
    resp = client.post("/fingerprints/evaluate", json=body)
    parsed = json.loads(resp.json()["details_json"])
    assert parsed["matched"] == 0
    assert parsed["total"] == 0


# ---------------------------------------------------------------------------
# details_json — produced by real evaluator, serialised by real service
# ---------------------------------------------------------------------------

def test_details_json_is_string():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert isinstance(resp.json()["details_json"], str)


def test_details_json_parses_as_dict():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    parsed = json.loads(resp.json()["details_json"])
    assert isinstance(parsed, dict)


def test_details_json_contains_matched_total_metrics():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    parsed = json.loads(resp.json()["details_json"])
    assert "matched" in parsed
    assert "total" in parsed
    assert "metrics" in parsed


def test_details_json_matched_is_integer():
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    parsed = json.loads(resp.json()["details_json"])
    assert isinstance(parsed["matched"], int)


def test_details_json_total_equals_threshold_count():
    """total in details must equal the number of threshold keys sent."""
    resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    parsed = json.loads(resp.json()["details_json"])
    assert parsed["total"] == len(VALID_BODY["thresholds"])
