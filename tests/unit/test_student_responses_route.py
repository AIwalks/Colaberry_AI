"""Unit tests for GET /sentinel/student-responses (Sprint 11).

Uses FastAPI TestClient. All DB queries are patched — no real database required.
"""

import os

os.environ.setdefault("API_KEY", "test-sentinel-key-sprint11")

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from config.auth import require_api_key
from api.routes.sentinel import _get_db_optional

_URL         = "/sentinel/student-responses"
_MSSQL_PATCH = "api.routes.sentinel.MSSQL_CONFIGURED"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _patch_auth():
    app.dependency_overrides[require_api_key] = lambda: None
    yield
    app.dependency_overrides.pop(require_api_key, None)


def _make_row(**kwargs) -> SimpleNamespace:
    """Return a SimpleNamespace that satisfies _serialize_student_response()."""
    defaults = dict(
        id=1,
        cbm_id=42,
        engagement_event_id=1001,
        user_id=101,
        response_channel="whatsapp",
        match_method="thread_id",
        confidence=1.0,
        matched_at=datetime(2026, 6, 20, 14, 30, 0),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ===========================================================================
# Mock-mode (MSSQL_CONFIGURED=False)
# ===========================================================================

class TestMockFallback:

    def test_returns_mock_data_when_no_db(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "mock"
        assert isinstance(data["responses"], list)
        assert len(data["responses"]) > 0
        assert data["total"] == len(data["responses"])

    def test_mock_row_has_required_fields(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        row = resp.json()["responses"][0]
        for field in ("id", "cbm_id", "engagement_event_id", "user_id",
                      "response_channel", "match_method", "confidence", "matched_at"):
            assert field in row, f"missing field: {field}"

    def test_mock_includes_deterministic_row(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        rows = resp.json()["responses"]
        assert any(r["confidence"] == 1.0 for r in rows)

    def test_mock_includes_heuristic_row(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        rows = resp.json()["responses"]
        assert any(r["confidence"] < 1.0 for r in rows)

    def test_mock_includes_thread_id_method(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        rows = resp.json()["responses"]
        assert any(r["match_method"] == "thread_id" for r in rows)

    def test_mock_includes_time_proximity_method(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL)
        rows = resp.json()["responses"]
        assert any(r["match_method"] == "time_proximity" for r in rows)

    def test_mock_user_id_filter(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL, params={"user_id": 101})
        rows = resp.json()["responses"]
        assert all(r["user_id"] == 101 for r in rows)
        assert len(rows) > 0

    def test_mock_cbm_id_filter(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL, params={"cbm_id": 42})
        rows = resp.json()["responses"]
        assert all(r["cbm_id"] == 42 for r in rows)
        assert len(rows) == 1

    def test_mock_user_id_filter_no_results(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL, params={"user_id": 9999})
        data = resp.json()
        assert data["responses"] == []
        assert data["total"] == 0

    def test_mock_combined_filter(self):
        with patch(_MSSQL_PATCH, False):
            resp = client.get(_URL, params={"user_id": 101, "cbm_id": 42})
        rows = resp.json()["responses"]
        assert all(r["user_id"] == 101 and r["cbm_id"] == 42 for r in rows)


# ===========================================================================
# DB-mode (MSSQL_CONFIGURED=True — mocked session)
# ===========================================================================

def _mock_db_with_rows(rows):
    """Return a context manager that yields a mock session returning `rows`."""
    mock_session = MagicMock()
    mock_query   = MagicMock()
    mock_session.query.return_value     = mock_query
    mock_query.filter.return_value      = mock_query
    mock_query.order_by.return_value    = mock_query
    mock_query.limit.return_value       = mock_query
    mock_query.all.return_value         = rows

    def _gen():
        yield mock_session

    return _gen


class TestDbMode:
    """DB-mode tests use dependency_overrides to inject a mock session.

    Patching the module attribute `_get_db_optional` does not work because
    FastAPI captures the function reference at route decoration time via
    Depends(_get_db_optional). dependency_overrides replaces the resolution
    at request time instead.
    """

    def _use_mock_db(self, rows):
        app.dependency_overrides[_get_db_optional] = _mock_db_with_rows(rows)

    def _clear_mock_db(self):
        app.dependency_overrides.pop(_get_db_optional, None)

    def test_db_mode_returns_serialized_rows(self):
        row = _make_row()
        self._use_mock_db([row])
        try:
            resp = client.get(_URL)
        finally:
            self._clear_mock_db()
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "db"
        assert len(data["responses"]) == 1
        r = data["responses"][0]
        assert r["cbm_id"]           == 42
        assert r["user_id"]          == 101
        assert r["response_channel"] == "whatsapp"
        assert r["match_method"]     == "thread_id"
        assert r["confidence"]       == 1.0
        assert r["matched_at"]       == "2026-06-20T14:30:00"

    def test_db_mode_empty_result(self):
        self._use_mock_db([])
        try:
            resp = client.get(_URL)
        finally:
            self._clear_mock_db()
        data = resp.json()
        assert data["responses"] == []
        assert data["total"]     == 0
        assert data["source"]    == "db"

    def test_db_mode_heuristic_confidence_serialized(self):
        row = _make_row(match_method="time_proximity", confidence=0.65)
        self._use_mock_db([row])
        try:
            resp = client.get(_URL)
        finally:
            self._clear_mock_db()
        r = resp.json()["responses"][0]
        assert r["confidence"]   == 0.65
        assert r["match_method"] == "time_proximity"

    def test_db_mode_null_matched_at_serialized_as_none(self):
        row = _make_row(matched_at=None)
        self._use_mock_db([row])
        try:
            resp = client.get(_URL)
        finally:
            self._clear_mock_db()
        r = resp.json()["responses"][0]
        assert r["matched_at"] is None
