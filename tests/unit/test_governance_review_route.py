"""Unit tests for governance review action endpoints (Sprint 9).

POST /sentinel/governance/reviews/{review_id}/approve
POST /sentinel/governance/reviews/{review_id}/reject
POST /sentinel/governance/reviews/{review_id}/defer

All tests use FastAPI TestClient. GovernanceReviewService is patched at its
import path in api.routes.sentinel so no real database is required.
"""

import os

# Set API_KEY before app import so require_api_key returns 403 (not 503) in auth tests.
os.environ.setdefault("API_KEY", "test-sentinel-key-sprint9")

import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from config.auth import require_api_key

# ---------------------------------------------------------------------------
# Patch paths
# ---------------------------------------------------------------------------

_SVC_PATCH   = "api.routes.sentinel.GovernanceReviewService"
_MSSQL_PATCH = "api.routes.sentinel.MSSQL_CONFIGURED"

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_APPROVE_URL = "/sentinel/governance/reviews/{id}/approve"
_REJECT_URL  = "/sentinel/governance/reviews/{id}/reject"
_DEFER_URL   = "/sentinel/governance/reviews/{id}/defer"


def _url(template: str, review_id: int = 1) -> str:
    return template.format(id=review_id)


# ---------------------------------------------------------------------------
# Test client
# ---------------------------------------------------------------------------

client = TestClient(app)


# ---------------------------------------------------------------------------
# Auth fixture — overrides require_api_key for every test; auth tests remove it.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_auth():
    app.dependency_overrides[require_api_key] = lambda: None
    yield
    app.dependency_overrides.pop(require_api_key, None)


# ---------------------------------------------------------------------------
# Mock review factory
# ---------------------------------------------------------------------------

def _make_review(status: str = "approved", **overrides) -> SimpleNamespace:
    """SimpleNamespace satisfying GovernanceReviewRead.model_validate()."""
    defaults = dict(
        id=1,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        updated_at=datetime(2026, 1, 1, 10, 0, 0),
        interpretation_id=10,
        entity_id="101",
        entity_type="student",
        status=status,
        reviewed_by="reviewer@test.com",
        reviewed_at=datetime(2026, 1, 1, 10, 0, 0),
        review_notes=None,
        governance_reason="Engagement risk — elevated dropout signal",
        risk_level="high",
        confidence=0.9,
        audit_snapshot_json=None,
        is_active=True,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ===========================================================================
# TestApproveEndpoint
# ===========================================================================

class TestApproveEndpoint:

    def test_approve_happy_path(self):
        review = _make_review(status="approved", reviewed_by="admin@test.com")
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
            mock_svc.return_value.approve_review.return_value = review
            response = client.post(
                _url(_APPROVE_URL),
                json={"reviewed_by": "admin@test.com", "review_notes": "Risk confirmed"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        kwargs = mock_svc.return_value.approve_review.call_args.kwargs
        assert kwargs["review_id"] == 1
        assert kwargs["reviewed_by"] == "admin@test.com"
        assert kwargs["review_notes"] == "Risk confirmed"

    def test_approve_not_found(self):
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
            mock_svc.return_value.approve_review.side_effect = ValueError(
                "GovernanceReview id=999 not found."
            )
            response = client.post(
                _url(_APPROVE_URL, review_id=999),
                json={"reviewed_by": "admin@test.com"},
            )
        assert response.status_code == 404

    def test_approve_empty_reviewed_by(self):
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH):
            response = client.post(
                _url(_APPROVE_URL),
                json={"reviewed_by": ""},
            )
        assert response.status_code == 422

    def test_approve_no_db(self):
        with patch(_MSSQL_PATCH, False), patch(_SVC_PATCH) as mock_svc:
            response = client.post(
                _url(_APPROVE_URL),
                json={"reviewed_by": "admin@test.com"},
            )
        assert response.status_code == 503
        mock_svc.return_value.approve_review.assert_not_called()

    def test_approve_no_api_key(self):
        app.dependency_overrides.pop(require_api_key, None)
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH):
            response = client.post(
                _url(_APPROVE_URL),
                json={"reviewed_by": "admin@test.com"},
            )
        assert response.status_code in (401, 403)


# ===========================================================================
# TestRejectEndpoint
# ===========================================================================

class TestRejectEndpoint:

    def test_reject_happy_path(self):
        review = _make_review(status="rejected", review_notes="Risk overstated")
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
            mock_svc.return_value.reject_review.return_value = review
            response = client.post(
                _url(_REJECT_URL),
                json={"reviewed_by": "admin@test.com", "review_notes": "Risk overstated"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        kwargs = mock_svc.return_value.reject_review.call_args.kwargs
        assert kwargs["review_notes"] == "Risk overstated"

    def test_reject_not_found(self):
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
            mock_svc.return_value.reject_review.side_effect = ValueError(
                "GovernanceReview id=999 not found."
            )
            response = client.post(
                _url(_REJECT_URL, review_id=999),
                json={"reviewed_by": "admin@test.com", "review_notes": "No reason"},
            )
        assert response.status_code == 404

    def test_reject_missing_review_notes(self):
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH):
            response = client.post(
                _url(_REJECT_URL),
                json={"reviewed_by": "admin@test.com"},
            )
        assert response.status_code == 422

    def test_reject_whitespace_review_notes(self):
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
            mock_svc.return_value.reject_review.side_effect = ValueError(
                "review_notes is required for rejection."
            )
            response = client.post(
                _url(_REJECT_URL),
                json={"reviewed_by": "admin@test.com", "review_notes": "   "},
            )
        assert response.status_code == 422

    def test_reject_no_db(self):
        with patch(_MSSQL_PATCH, False), patch(_SVC_PATCH) as mock_svc:
            response = client.post(
                _url(_REJECT_URL),
                json={"reviewed_by": "admin@test.com", "review_notes": "Bad data"},
            )
        assert response.status_code == 503
        mock_svc.return_value.reject_review.assert_not_called()

    def test_reject_no_api_key(self):
        app.dependency_overrides.pop(require_api_key, None)
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH):
            response = client.post(
                _url(_REJECT_URL),
                json={"reviewed_by": "admin@test.com", "review_notes": "Reason"},
            )
        assert response.status_code in (401, 403)


# ===========================================================================
# TestDeferEndpoint
# ===========================================================================

class TestDeferEndpoint:

    def test_defer_happy_path(self):
        review = _make_review(status="deferred", governance_reason="Awaiting updated data")
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
            mock_svc.return_value.defer_review.return_value = review
            response = client.post(
                _url(_DEFER_URL),
                json={"reviewed_by": "admin@test.com", "governance_reason": "Awaiting updated data"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deferred"
        kwargs = mock_svc.return_value.defer_review.call_args.kwargs
        assert kwargs["governance_reason"] == "Awaiting updated data"

    def test_defer_not_found(self):
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
            mock_svc.return_value.defer_review.side_effect = ValueError(
                "GovernanceReview id=999 not found."
            )
            response = client.post(
                _url(_DEFER_URL, review_id=999),
                json={"reviewed_by": "admin@test.com", "governance_reason": "Need more data"},
            )
        assert response.status_code == 404

    def test_defer_missing_governance_reason(self):
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH):
            response = client.post(
                _url(_DEFER_URL),
                json={"reviewed_by": "admin@test.com"},
            )
        assert response.status_code == 422

    def test_defer_whitespace_governance_reason(self):
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH) as mock_svc:
            mock_svc.return_value.defer_review.side_effect = ValueError(
                "governance_reason is required for deferral."
            )
            response = client.post(
                _url(_DEFER_URL),
                json={"reviewed_by": "admin@test.com", "governance_reason": "   "},
            )
        assert response.status_code == 422

    def test_defer_no_db(self):
        with patch(_MSSQL_PATCH, False), patch(_SVC_PATCH) as mock_svc:
            response = client.post(
                _url(_DEFER_URL),
                json={"reviewed_by": "admin@test.com", "governance_reason": "Need data"},
            )
        assert response.status_code == 503
        mock_svc.return_value.defer_review.assert_not_called()

    def test_defer_no_api_key(self):
        app.dependency_overrides.pop(require_api_key, None)
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH):
            response = client.post(
                _url(_DEFER_URL),
                json={"reviewed_by": "admin@test.com", "governance_reason": "Need data"},
            )
        assert response.status_code in (401, 403)


# ===========================================================================
# TestAuthGuard — canonical auth coverage across all three action endpoints
# ===========================================================================

class TestAuthGuard:

    def _no_auth_post(self, url: str, body: dict) -> int:
        app.dependency_overrides.pop(require_api_key, None)
        with patch(_MSSQL_PATCH, True), patch(_SVC_PATCH):
            response = client.post(url, json=body)
        return response.status_code

    def test_approve_requires_api_key(self):
        assert self._no_auth_post(_url(_APPROVE_URL), {"reviewed_by": "x"}) in (401, 403)

    def test_reject_requires_api_key(self):
        assert self._no_auth_post(
            _url(_REJECT_URL), {"reviewed_by": "x", "review_notes": "reason"}
        ) in (401, 403)

    def test_defer_requires_api_key(self):
        assert self._no_auth_post(
            _url(_DEFER_URL), {"reviewed_by": "x", "governance_reason": "reason"}
        ) in (401, 403)
