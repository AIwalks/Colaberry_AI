"""Unit tests for POST /insight/generate — API contract, no DB required."""

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

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_BODY = {"entity_id": "s1", "entity_type": "student"}

EXPECTED_RESPONSE_KEYS = {
    "generated_count",
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
}


def make_insight_dict(
    id: int = 1,
    title: str = "High-confidence KPI: avg_logins",
    body: str = "KPI 'avg_logins' has confidence 0.8 for entity type 'student'.",
    insight_type: str = "kpi",
    entity_type: str = "student",
    entity_id: str = "0",
    confidence: float = 0.8,
) -> dict:
    return {
        "id": id,
        "title": title,
        "body": body,
        "insight_type": insight_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "confidence": confidence,
    }


def make_service_result(insights: list, analyzed_kpis: int = 1,
                        analyzed_fingerprints: int = 0) -> dict:
    return {
        "generated_count": len(insights),
        "analyzed_kpis": analyzed_kpis,
        "analyzed_fingerprints": analyzed_fingerprints,
        "insights": insights,
    }


# ---------------------------------------------------------------------------
# Valid request returns 200
# ---------------------------------------------------------------------------

def test_valid_request_returns_200():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict()]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert resp.status_code == 200


def test_valid_request_returns_json():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict()]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert "application/json" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Response fields match InsightGenerateResponse schema
# ---------------------------------------------------------------------------

def test_response_contains_all_top_level_keys():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict()]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert set(resp.json().keys()) == EXPECTED_RESPONSE_KEYS


def test_generated_count_is_integer():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict()]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert isinstance(resp.json()["generated_count"], int)


def test_analyzed_kpis_is_integer():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([], analyzed_kpis=3),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert isinstance(resp.json()["analyzed_kpis"], int)


def test_analyzed_fingerprints_is_integer():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([], analyzed_fingerprints=5),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert isinstance(resp.json()["analyzed_fingerprints"], int)


def test_insights_is_a_list():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict()]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert isinstance(resp.json()["insights"], list)


# ---------------------------------------------------------------------------
# Response contains insight list — single insight field validation
# ---------------------------------------------------------------------------

def test_single_insight_appears_in_response():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict()]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert len(resp.json()["insights"]) == 1


def test_insight_contains_all_expected_keys():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict()]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    insight = resp.json()["insights"][0]
    assert set(insight.keys()) == EXPECTED_INSIGHT_KEYS


def test_insight_id_is_integer():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict(id=1)]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert isinstance(resp.json()["insights"][0]["id"], int)


def test_insight_entity_id_is_string():
    """entity_id is cast to str in the service — must come back as string."""
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict(entity_id="42")]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert isinstance(resp.json()["insights"][0]["entity_id"], str)


def test_insight_confidence_is_float():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([make_insight_dict(confidence=0.8)]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert isinstance(resp.json()["insights"][0]["confidence"], float)


def test_insight_type_is_kpi_or_risk():
    for insight_type in ("kpi", "risk"):
        with patch(
            "api.routes.insight.InsightService.generate_insights",
            return_value=make_service_result([make_insight_dict(insight_type=insight_type)]),
        ):
            resp = client.post("/insight/generate", json=VALID_BODY)
        assert resp.json()["insights"][0]["insight_type"] == insight_type


def test_generated_count_matches_insights_list_length():
    insights = [make_insight_dict(id=1), make_insight_dict(id=2)]
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result(insights),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    data = resp.json()
    assert data["generated_count"] == len(data["insights"])


# ---------------------------------------------------------------------------
# Empty result handled
# ---------------------------------------------------------------------------

def test_empty_result_returns_200():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert resp.status_code == 200


def test_empty_result_generated_count_is_zero():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert resp.json()["generated_count"] == 0


def test_empty_result_insights_is_empty_list():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([]),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    assert resp.json()["insights"] == []


def test_empty_result_analyzed_counts_are_present():
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([], analyzed_kpis=2, analyzed_fingerprints=3),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    data = resp.json()
    assert data["analyzed_kpis"] == 2
    assert data["analyzed_fingerprints"] == 3


# ---------------------------------------------------------------------------
# Multiple insights handled
# ---------------------------------------------------------------------------

def test_multiple_insights_all_present_in_response():
    insights = [
        make_insight_dict(id=1, insight_type="kpi"),
        make_insight_dict(id=2, insight_type="risk", title="High-risk pattern: disengagement"),
    ]
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result(insights),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    data = resp.json()
    assert data["generated_count"] == 2
    assert len(data["insights"]) == 2


def test_multiple_insights_each_has_all_expected_keys():
    insights = [make_insight_dict(id=i) for i in range(1, 4)]
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result(insights),
    ):
        resp = client.post("/insight/generate", json=VALID_BODY)
    for insight in resp.json()["insights"]:
        assert set(insight.keys()) == EXPECTED_INSIGHT_KEYS


# ---------------------------------------------------------------------------
# Route accepts no request body — no 422 on empty POST
# ---------------------------------------------------------------------------

def test_post_with_no_body_returns_422():
    """Route requires entity_id and entity_type — missing body must return 422."""
    resp = client.post("/insight/generate")
    assert resp.status_code == 422


def test_post_with_extra_fields_still_returns_200():
    """Extra body fields are ignored by Pydantic — required fields present must succeed."""
    with patch(
        "api.routes.insight.InsightService.generate_insights",
        return_value=make_service_result([]),
    ):
        resp = client.post("/insight/generate", json={**VALID_BODY, "unexpected": "data"})
    assert resp.status_code == 200
