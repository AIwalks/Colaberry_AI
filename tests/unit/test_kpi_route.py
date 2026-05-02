"""Unit tests for POST /kpi/discover — API contract, no DB required."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from config.database import get_db
from core.kpi_discovery.models import DiscoveredKPI, KPIDiscoveryResult


# ---------------------------------------------------------------------------
# Fake DB session — replaces get_db dependency
# ---------------------------------------------------------------------------

def fake_db():
    yield MagicMock()


app.dependency_overrides[get_db] = fake_db

client = TestClient(app, headers={"X-Api-Key": "test-key"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_discovered_kpi(kpi_name: str = "avg_logins") -> DiscoveredKPI:
    return DiscoveredKPI(
        kpi_name=kpi_name,
        source_pattern="auto",
        entity_type="student",
        formula="avg(logins)",
        confidence=0.8,
        sample_size=10,
    )


def make_result(kpi_names: list) -> KPIDiscoveryResult:
    kpis = {name: make_discovered_kpi(name) for name in kpi_names}
    return KPIDiscoveryResult(
        kpis=kpis,
        analyzed_count=len(kpi_names),
        metadata={},
    )


# ---------------------------------------------------------------------------
# Valid request returns 200
# ---------------------------------------------------------------------------

def test_valid_request_returns_200():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins"]),
    ):
        resp = client.post("/kpi/discover")
    assert resp.status_code == 200


def test_valid_request_returns_json():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins"]),
    ):
        resp = client.post("/kpi/discover")
    assert "application/json" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Response fields match schema
# ---------------------------------------------------------------------------

def test_response_contains_kpis_found_and_kpis_keys():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins"]),
    ):
        resp = client.post("/kpi/discover")
    data = resp.json()
    assert "kpis_found" in data
    assert "kpis" in data


def test_kpis_found_is_integer():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins"]),
    ):
        resp = client.post("/kpi/discover")
    assert isinstance(resp.json()["kpis_found"], int)


def test_kpis_is_a_list():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins"]),
    ):
        resp = client.post("/kpi/discover")
    assert isinstance(resp.json()["kpis"], list)


def test_kpis_list_contains_strings():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins"]),
    ):
        resp = client.post("/kpi/discover")
    for item in resp.json()["kpis"]:
        assert isinstance(item, str)


# ---------------------------------------------------------------------------
# Response contains KPI list
# ---------------------------------------------------------------------------

def test_single_kpi_appears_in_response_list():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins"]),
    ):
        resp = client.post("/kpi/discover")
    data = resp.json()
    assert data["kpis_found"] == 1
    assert "avg_logins" in data["kpis"]


def test_multiple_kpis_all_appear_in_response_list():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins", "avg_sessions"]),
    ):
        resp = client.post("/kpi/discover")
    data = resp.json()
    assert data["kpis_found"] == 2
    assert "avg_logins" in data["kpis"]
    assert "avg_sessions" in data["kpis"]


def test_kpis_found_matches_kpis_list_length():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins", "avg_sessions", "avg_score"]),
    ):
        resp = client.post("/kpi/discover")
    data = resp.json()
    assert data["kpis_found"] == len(data["kpis"])


# ---------------------------------------------------------------------------
# Empty input returns empty list
# ---------------------------------------------------------------------------

def test_empty_kpi_result_returns_200():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result([]),
    ):
        resp = client.post("/kpi/discover")
    assert resp.status_code == 200


def test_empty_kpi_result_kpis_found_is_zero():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result([]),
    ):
        resp = client.post("/kpi/discover")
    assert resp.json()["kpis_found"] == 0


def test_empty_kpi_result_kpis_is_empty_list():
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result([]),
    ):
        resp = client.post("/kpi/discover")
    assert resp.json()["kpis"] == []


# ---------------------------------------------------------------------------
# Route accepts no request body (no 422 on empty POST)
# ---------------------------------------------------------------------------

def test_post_with_no_body_is_accepted():
    """Route takes no request body — posting nothing must not return 422."""
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins"]),
    ):
        resp = client.post("/kpi/discover")
    assert resp.status_code == 200


def test_post_with_unexpected_json_body_still_returns_200():
    """Route ignores any body — extra fields must not cause an error."""
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins"]),
    ):
        resp = client.post("/kpi/discover", json={"unexpected": "field"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Malformed / edge-case service data
# ---------------------------------------------------------------------------

def test_kpi_name_is_preserved_exactly():
    """KPI names must be returned verbatim, not transformed."""
    with patch(
        "api.routes.kpi.KPIDiscoveryService.discover_kpis",
        return_value=make_result(["avg_logins_per_week"]),
    ):
        resp = client.post("/kpi/discover")
    assert resp.json()["kpis"] == ["avg_logins_per_week"]


def test_kpis_found_is_non_negative():
    for count in (0, 1, 3):
        names = [f"kpi_{i}" for i in range(count)]
        with patch(
            "api.routes.kpi.KPIDiscoveryService.discover_kpis",
            return_value=make_result(names),
        ):
            resp = client.post("/kpi/discover")
        assert resp.json()["kpis_found"] >= 0
