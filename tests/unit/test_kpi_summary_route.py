"""Unit tests for GET /sentinel/kpi-summary (Sprint 11 — Task 2).

Uses FastAPI TestClient. All DB queries are patched — no real database required.
"""

import os

os.environ.setdefault("API_KEY", "test-sentinel-key-kpi")

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from config.auth import require_api_key
from api.routes.sentinel import _get_db_optional

_URL         = "/sentinel/kpi-summary"
_MSSQL_PATCH = "api.routes.sentinel.MSSQL_CONFIGURED"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _patch_auth():
    app.dependency_overrides[require_api_key] = lambda: None
    yield
    app.dependency_overrides.pop(require_api_key, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_with_counts(pending: int, approved: int, total_responses: int, suppressed: int):
    """Return a dependency-override generator that yields a mock session.

    The mock session is configured to return the given counts for
    GovernanceReview and StudentResponse .count() calls in the order the
    endpoint issues them.
    """
    mock_session = MagicMock()

    # Each .query(...).filter(...).count() call is a new chain from the session.
    # We pre-program the exact order the endpoint calls them.
    mock_session.query.return_value.filter.return_value.count.side_effect = [
        pending,      # GovernanceReview status='pending'
        approved,     # GovernanceReview status='approved'
        suppressed,   # StudentResponse confidence=1.0
    ]
    # StudentResponse total (no filter) — query(...).count()
    mock_session.query.return_value.count.return_value = total_responses

    def _gen():
        yield mock_session

    return _gen


# ---------------------------------------------------------------------------
# Mock-mode tests (MSSQL_CONFIGURED=False)
# ---------------------------------------------------------------------------

class TestMockFallback:

    def test_returns_200(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        assert resp.status_code == 200

    def test_source_is_mock(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        assert resp.json()["source"] == "mock"

    def test_pending_reviews_is_integer(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        assert isinstance(resp.json()["pending_reviews"], int)

    def test_approved_reviews_is_integer(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        assert isinstance(resp.json()["approved_reviews"], int)

    def test_student_responses_is_integer(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        assert isinstance(resp.json()["student_responses"], int)

    def test_suppressed_retriggers_is_integer(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        assert isinstance(resp.json()["suppressed_retriggers"], int)

    def test_all_four_fields_present(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        data = resp.json()
        for field in ("pending_reviews", "approved_reviews", "student_responses", "suppressed_retriggers"):
            assert field in data, f"missing field: {field}"

    def test_mock_values_match_mock_data(self):
        """Mock constants must be consistent with the actual mock review/response lists."""
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        data = resp.json()
        # _MOCK_REVIEWS has 3 pending (IDs 1,2,3) and 2 approved (IDs 4,5)
        assert data["pending_reviews"]       == 3
        assert data["approved_reviews"]      == 2
        # _MOCK_STUDENT_RESPONSES has 4 total; 2 with confidence=1.0
        assert data["student_responses"]     == 4
        assert data["suppressed_retriggers"] == 2

    def test_no_api_key_returns_403(self):
        """Auth guard is enforced even on the KPI endpoint."""
        app.dependency_overrides.pop(require_api_key, None)
        try:
            with patch(_MSSQL_PATCH, False):
                resp = client.get(_URL)
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[require_api_key] = lambda: None


# ---------------------------------------------------------------------------
# DB-mode tests (MSSQL_CONFIGURED=True — mocked session)
# ---------------------------------------------------------------------------

class TestDbMode:
    """Uses app.dependency_overrides to inject a mock session (same fix as
    test_student_responses_route.py — patching the module attribute does not
    work because Depends() captures the function reference at decoration time)."""

    def _use_mock(self, pending, approved, responses, suppressed):
        app.dependency_overrides[_get_db_optional] = _mock_db_with_counts(
            pending, approved, responses, suppressed
        )

    def _clear_mock(self):
        app.dependency_overrides.pop(_get_db_optional, None)

    def test_returns_200_in_db_mode(self):
        self._use_mock(5, 3, 12, 7)
        try:
            resp = client.get(_URL)
        finally:
            self._clear_mock()
        assert resp.status_code == 200

    def test_source_is_db(self):
        self._use_mock(5, 3, 12, 7)
        try:
            resp = client.get(_URL)
        finally:
            self._clear_mock()
        assert resp.json()["source"] == "db"

    def test_db_counts_propagated(self):
        self._use_mock(pending=5, approved=3, responses=12, suppressed=7)
        try:
            resp = client.get(_URL)
        finally:
            self._clear_mock()
        data = resp.json()
        assert data["pending_reviews"]       == 5
        assert data["approved_reviews"]      == 3
        assert data["student_responses"]     == 12
        assert data["suppressed_retriggers"] == 7

    def test_zero_counts_are_valid(self):
        self._use_mock(0, 0, 0, 0)
        try:
            resp = client.get(_URL)
        finally:
            self._clear_mock()
        data = resp.json()
        assert data["pending_reviews"]       == 0
        assert data["suppressed_retriggers"] == 0
