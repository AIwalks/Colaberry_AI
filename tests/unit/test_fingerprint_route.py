"""Unit tests for POST /fingerprints/evaluate — API contract, no DB required."""

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from config.database import get_db


# ---------------------------------------------------------------------------
# Fake DB session — replaces get_db dependency
# ---------------------------------------------------------------------------

def fake_db():
    yield MagicMock()


app.dependency_overrides[get_db] = fake_db

client = TestClient(app, headers={"X-Api-Key": "test-key"})


# ---------------------------------------------------------------------------
# Fake ORM record returned by FingerprintService.evaluate_and_store
# ---------------------------------------------------------------------------

def make_fake_record(
    id: int = 1,
    entity_type: str = "student",
    entity_id: str = "student_42",
    pattern_name: str = "disengagement",
    score: float = 0.8,
    risk_level: str = "high",
    details_json: str = '{"matched": 2, "total": 2, "metrics": {"logins": 10}}',
):
    record = MagicMock()
    record.id = id
    record.entity_type = entity_type
    record.entity_id = entity_id
    record.pattern_name = pattern_name
    record.score = score
    record.risk_level = risk_level
    record.details_json = details_json
    return record


VALID_BODY = {
    "entity_type": "student",
    "entity_id": "student_42",
    "pattern_name": "disengagement",
    "thresholds": {"logins": 5},
    "metrics": {"logins": 10},
}

EXPECTED_RESPONSE_KEYS = {
    "id",
    "entity_type",
    "entity_id",
    "pattern_name",
    "score",
    "risk_level",
    "details_json",
}


# ---------------------------------------------------------------------------
# Happy path — valid request returns 200
# ---------------------------------------------------------------------------

def test_valid_request_returns_200():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert resp.status_code == 200


def test_valid_request_returns_correct_content_type():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert "application/json" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Response fields match FingerprintResponse schema
# ---------------------------------------------------------------------------

def test_response_contains_all_expected_keys():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert set(resp.json().keys()) == EXPECTED_RESPONSE_KEYS


def test_response_id_is_integer():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(id=7),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert resp.json()["id"] == 7


def test_response_entity_type_echoed():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(entity_type="cohort"),
    ):
        body = {**VALID_BODY, "entity_type": "cohort"}
        resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["entity_type"] == "cohort"


def test_response_entity_id_echoed():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(entity_id="s99"),
    ):
        body = {**VALID_BODY, "entity_id": "s99"}
        resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["entity_id"] == "s99"


def test_response_pattern_name_echoed():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(pattern_name="re-engagement"),
    ):
        body = {**VALID_BODY, "pattern_name": "re-engagement"}
        resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["pattern_name"] == "re-engagement"


# ---------------------------------------------------------------------------
# Score is a float between 0.0 and 1.0
# ---------------------------------------------------------------------------

def test_response_score_is_float():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(score=0.5),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert isinstance(resp.json()["score"], float)


def test_response_score_is_between_0_and_1():
    for score in (0.0, 0.5, 0.8, 1.0):
        with patch(
            "api.routes.fingerprint.FingerprintService.evaluate_and_store",
            return_value=make_fake_record(score=score),
        ):
            resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
        assert 0.0 <= resp.json()["score"] <= 1.0, f"score {score} out of range"


# ---------------------------------------------------------------------------
# risk_level is one of the valid values
# ---------------------------------------------------------------------------

def test_response_risk_level_is_valid():
    for risk in ("low", "medium", "high"):
        with patch(
            "api.routes.fingerprint.FingerprintService.evaluate_and_store",
            return_value=make_fake_record(risk_level=risk),
        ):
            resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
        assert resp.json()["risk_level"] in {"low", "medium", "high"}


def test_response_risk_level_high_when_service_returns_high():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(risk_level="high"),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert resp.json()["risk_level"] == "high"


def test_response_risk_level_low_when_service_returns_low():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(score=0.0, risk_level="low"),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert resp.json()["risk_level"] == "low"


# ---------------------------------------------------------------------------
# details_json is a valid JSON string
# ---------------------------------------------------------------------------

def test_details_json_is_a_string():
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    assert isinstance(resp.json()["details_json"], str)


def test_details_json_parses_without_error():
    details = '{"matched": 2, "total": 2, "metrics": {"logins": 10}}'
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(details_json=details),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    parsed = json.loads(resp.json()["details_json"])
    assert isinstance(parsed, dict)


def test_details_json_contains_matched_and_total_keys():
    details = '{"matched": 1, "total": 2, "metrics": {}}'
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(details_json=details),
    ):
        resp = client.post("/fingerprints/evaluate", json=VALID_BODY)
    parsed = json.loads(resp.json()["details_json"])
    assert "matched" in parsed
    assert "total" in parsed


# ---------------------------------------------------------------------------
# Missing required fields → 422
# ---------------------------------------------------------------------------

def test_missing_entity_type_returns_422():
    body = {k: v for k, v in VALID_BODY.items() if k != "entity_type"}
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.status_code == 422


def test_missing_entity_id_returns_422():
    body = {k: v for k, v in VALID_BODY.items() if k != "entity_id"}
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.status_code == 422


def test_missing_pattern_name_returns_422():
    body = {k: v for k, v in VALID_BODY.items() if k != "pattern_name"}
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.status_code == 422


def test_missing_thresholds_returns_422():
    body = {k: v for k, v in VALID_BODY.items() if k != "thresholds"}
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.status_code == 422


def test_missing_metrics_returns_422():
    body = {k: v for k, v in VALID_BODY.items() if k != "metrics"}
    resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.status_code == 422


def test_empty_body_returns_422():
    resp = client.post("/fingerprints/evaluate", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Empty thresholds — valid request, deterministic low/0.0 result
# ---------------------------------------------------------------------------

def test_empty_thresholds_returns_200():
    body = {**VALID_BODY, "thresholds": {}}
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(score=0.0, risk_level="low",
                                     details_json='{"matched": 0, "total": 0, "metrics": {}}'),
    ):
        resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.status_code == 200


def test_empty_thresholds_score_is_zero():
    body = {**VALID_BODY, "thresholds": {}}
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(score=0.0, risk_level="low",
                                     details_json='{"matched": 0, "total": 0, "metrics": {}}'),
    ):
        resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["score"] == 0.0


def test_empty_thresholds_risk_level_is_low():
    body = {**VALID_BODY, "thresholds": {}}
    with patch(
        "api.routes.fingerprint.FingerprintService.evaluate_and_store",
        return_value=make_fake_record(score=0.0, risk_level="low",
                                     details_json='{"matched": 0, "total": 0, "metrics": {}}'),
    ):
        resp = client.post("/fingerprints/evaluate", json=body)
    assert resp.json()["risk_level"] == "low"
