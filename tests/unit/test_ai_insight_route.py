"""Unit tests for POST /insight/generate/ai — feature-flagged AI insight route.

Tests cover:
  - Feature flag disabled  → ai_enabled=False, empty insights, no Claude call
  - Feature flag enabled   → 200, correct AI insight shape and field values
  - AI fallback state      → route returns 200 even when Claude is unavailable
  - Auth enforcement       → missing/wrong key returns 403
  - Request validation     → missing body returns 422
  - Existing route safety  → /insight/generate is unaffected
"""

import os
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
# Fixtures
# ---------------------------------------------------------------------------

VALID_BODY = {"entity_id": "student_101", "entity_type": "student"}

_VALID_AI_RESULT = {
    "summary": "Student shows strong disengagement signals across login frequency and session duration.",
    "risk_level": "high",
    "confidence": 0.89,
    "recommended_action": "Schedule a 1:1 check-in within 48 hours.",
    "explainability": [
        "Login frequency KPI has 92% confidence disengagement pattern.",
        "Session duration drop indicates active avoidance (81% confidence).",
    ],
}

_FALLBACK_AI_RESULT = {
    "summary": "AI insight unavailable. Review KPI data manually.",
    "risk_level": "unknown",
    "confidence": 0.0,
    "recommended_action": "Manual review required — AI service did not return a result.",
    "explainability": ["AI service unavailable — this is a safe fallback response."],
}

_KPI_DATA = [
    {
        "kpi_name": "avg_logins_per_week",
        "source_pattern": "disengagement",
        "entity_type": "student",
        "formula": "avg",
        "confidence": 0.92,
        "sample_size": 120,
    },
    {
        "kpi_name": "session_duration_drop",
        "source_pattern": "dropout_risk",
        "entity_type": "student",
        "formula": "delta",
        "confidence": 0.81,
        "sample_size": 85,
    },
]

_FINGERPRINT_DATA = [
    {
        "entity_type": "student",
        "entity_id": "student_101",
        "pattern_name": "disengagement",
        "score": 1.0,
        "risk_level": "high",
    }
]

EXPECTED_TOP_LEVEL_KEYS = {
    "ai_enabled",
    "entity_id",
    "entity_type",
    "analyzed_kpis",
    "analyzed_fingerprints",
    "insights",
}

EXPECTED_INSIGHT_KEYS = {
    "id",
    "title",
    "body",
    "insight_type",
    "entity_type",
    "entity_id",
    "confidence",
    "explanation",
    "recommended_action",
    "risk_level",
    "explainability",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enabled_request(monkeypatch, kpis=None, fingerprints=None, ai_result=None):
    """Set the feature flag and return patched context for a single enabled request."""
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    return (
        patch("api.routes.insight.InsightService.load_kpis", return_value=kpis or _KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=fingerprints or _FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=ai_result or _VALID_AI_RESULT),
    )


# ---------------------------------------------------------------------------
# Feature flag DISABLED
# ---------------------------------------------------------------------------

def test_flag_disabled_returns_200(monkeypatch):
    monkeypatch.delenv("ENABLE_AI_INSIGHTS", raising=False)
    resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.status_code == 200


def test_flag_disabled_ai_enabled_is_false(monkeypatch):
    monkeypatch.delenv("ENABLE_AI_INSIGHTS", raising=False)
    resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["ai_enabled"] is False


def test_flag_disabled_returns_empty_insights(monkeypatch):
    monkeypatch.delenv("ENABLE_AI_INSIGHTS", raising=False)
    resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["insights"] == []


def test_flag_disabled_includes_message(monkeypatch):
    monkeypatch.delenv("ENABLE_AI_INSIGHTS", raising=False)
    resp = client.post("/insight/generate/ai", json=VALID_BODY)
    msg = resp.json()["message"]
    assert msg is not None and len(msg) > 0


def test_flag_disabled_does_not_call_generate_ai_insight(monkeypatch):
    monkeypatch.delenv("ENABLE_AI_INSIGHTS", raising=False)
    with patch("api.routes.insight.generate_ai_insight") as mock_ai:
        client.post("/insight/generate/ai", json=VALID_BODY)
    mock_ai.assert_not_called()


def test_flag_false_string_is_also_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "false")
    resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["ai_enabled"] is False


def test_flag_true_uppercase_enables_route(monkeypatch):
    """ENABLE_AI_INSIGHTS check is case-insensitive."""
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "TRUE")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["ai_enabled"] is True


# ---------------------------------------------------------------------------
# Feature flag ENABLED — success path
# ---------------------------------------------------------------------------

def test_flag_enabled_returns_200(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.status_code == 200


def test_flag_enabled_ai_enabled_is_true(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["ai_enabled"] is True


def test_flag_enabled_response_has_required_top_level_keys(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert EXPECTED_TOP_LEVEL_KEYS.issubset(resp.json().keys())


def test_flag_enabled_returns_one_insight(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert len(resp.json()["insights"]) == 1


def test_ai_insight_has_required_fields(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert EXPECTED_INSIGHT_KEYS.issubset(resp.json()["insights"][0].keys())


def test_ai_insight_type_is_ai(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["insights"][0]["insight_type"] == "ai"


def test_ai_insight_confidence_matches_ai_result(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["insights"][0]["confidence"] == 0.89


def test_ai_insight_risk_level_in_title(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert "HIGH" in resp.json()["insights"][0]["title"]


def test_ai_insight_body_is_summary(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["insights"][0]["body"] == _VALID_AI_RESULT["summary"]


def test_ai_insight_explainability_is_list(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert isinstance(resp.json()["insights"][0]["explainability"], list)


def test_ai_insight_explanation_joins_explainability(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    insight = resp.json()["insights"][0]
    expected = "; ".join(_VALID_AI_RESULT["explainability"])
    assert insight["explanation"] == expected


def test_analyzed_counts_match_loaded_data(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    data = resp.json()
    assert data["analyzed_kpis"] == len(_KPI_DATA)
    assert data["analyzed_fingerprints"] == len(_FINGERPRINT_DATA)


def test_generate_ai_insight_called_once(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT) as mock_ai,
    ):
        client.post("/insight/generate/ai", json=VALID_BODY)
    mock_ai.assert_called_once()


def test_student_data_passed_to_generate_ai_insight(monkeypatch):
    """Route must pass entity_id, entity_type, kpis, and fingerprints to the AI service."""
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT) as mock_ai,
    ):
        client.post("/insight/generate/ai", json=VALID_BODY)
    call_arg = mock_ai.call_args[0][0]
    assert call_arg["entity_id"] == "student_101"
    assert call_arg["entity_type"] == "student"
    assert call_arg["kpis"] == _KPI_DATA
    assert call_arg["fingerprints"] == _FINGERPRINT_DATA


# ---------------------------------------------------------------------------
# AI fallback state — Claude unavailable, route still returns 200
# ---------------------------------------------------------------------------

def test_ai_fallback_returns_200(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=[]),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=[]),
        patch("api.routes.insight.generate_ai_insight", return_value=_FALLBACK_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.status_code == 200


def test_ai_fallback_insight_has_unknown_risk_level(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=[]),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=[]),
        patch("api.routes.insight.generate_ai_insight", return_value=_FALLBACK_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["insights"][0]["risk_level"] == "unknown"


def test_ai_fallback_confidence_is_zero(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=[]),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=[]),
        patch("api.routes.insight.generate_ai_insight", return_value=_FALLBACK_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["insights"][0]["confidence"] == 0.0


def test_ai_fallback_ai_enabled_remains_true(monkeypatch):
    """Feature flag is enabled; the fallback is an AI-layer failure, not a flag state."""
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=[]),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=[]),
        patch("api.routes.insight.generate_ai_insight", return_value=_FALLBACK_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.json()["ai_enabled"] is True


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------

def test_missing_api_key_returns_403():
    unauthenticated = TestClient(app)
    resp = unauthenticated.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.status_code == 403


def test_wrong_api_key_returns_403():
    bad_client = TestClient(app, headers={"X-Api-Key": "wrong-key"})
    resp = bad_client.post("/insight/generate/ai", json=VALID_BODY)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------

def test_missing_body_returns_422():
    resp = client.post("/insight/generate/ai")
    assert resp.status_code == 422


def test_extra_body_fields_ignored(monkeypatch):
    monkeypatch.setenv("ENABLE_AI_INSIGHTS", "true")
    with (
        patch("api.routes.insight.InsightService.load_kpis", return_value=_KPI_DATA),
        patch("api.routes.insight.InsightService.load_fingerprints", return_value=_FINGERPRINT_DATA),
        patch("api.routes.insight.generate_ai_insight", return_value=_VALID_AI_RESULT),
    ):
        resp = client.post("/insight/generate/ai", json={**VALID_BODY, "unexpected": "data"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Existing route safety — /insight/generate must be unaffected
# ---------------------------------------------------------------------------

def test_existing_route_still_returns_200():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value={
            "generated_count": 0,
            "analyzed_kpis": 0,
            "analyzed_fingerprints": 0,
            "insights": [],
        },
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert resp.status_code == 200


def test_existing_route_returns_generated_count_field():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value={
            "generated_count": 2,
            "analyzed_kpis": 3,
            "analyzed_fingerprints": 1,
            "insights": [],
        },
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert "generated_count" in resp.json()
