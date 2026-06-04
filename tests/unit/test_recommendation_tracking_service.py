"""Unit tests for services/recommendation_tracking_service.py.

All tests use mock DB sessions — no live DB or MSSQL required.

Coverage
────────
- record() happy path: row created with correct field values
- record() idempotency: active row returned, no duplicate inserted
- record() inactive bypass: invalidated row does not block a new insert
- record() non-fatal: DB error returns None, does not raise
- Context serialization: standard types, datetime, Decimal, unknown types
- invalidate() happy path: is_active, invalidated_at, reason all set
- invalidate() no-op: missing row handled silently
- invalidate() non-fatal: DB error does not raise
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from services.recommendation_tracking_service import (
    RecommendationTrackingService,
    _serialize_context,
)
from services.models import Recommendation


# ===========================================================================
# Helpers
# ===========================================================================

def _svc() -> RecommendationTrackingService:
    return RecommendationTrackingService()


def _make_db(
    *,
    existing: Optional[object] = None,
) -> MagicMock:
    """Return a mock session whose query chain returns `existing` from .first()."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing
    return db


_BASE_KWARGS = dict(
    cbm_id                = 42,
    interpretation_id     = 7,
    entity_id             = "student_001",
    recommendation_type   = "reach_out",
    recommendation_key    = "attendance_outreach",
    recommendation_text   = "Contact student about missed sessions.",
    dimension             = "attendance",
    risk_level            = "high",
    confidence            = 0.87,
    recommendation_context= {"last_activity_days": 18, "attendance_percentage": 0.22},
    generated_by          = "interpret_kpi_skill",
    model_name            = "claude-sonnet-4-6",
)


# ===========================================================================
# _serialize_context — unit tests for the helper directly
# ===========================================================================

class TestSerializeContext:

    def test_standard_types_round_trip(self):
        ctx = {"risk": "high", "days": 18, "pct": 0.22, "flag": True}
        result = json.loads(_serialize_context(ctx))
        assert result == ctx

    def test_datetime_converted_to_iso_string(self):
        dt = datetime(2026, 5, 30, 10, 0, 0)
        result = json.loads(_serialize_context({"ts": dt}))
        assert result["ts"] == dt.isoformat()

    def test_decimal_converted_to_float(self):
        result = json.loads(_serialize_context({"score": Decimal("0.75")}))
        assert abs(result["score"] - 0.75) < 1e-9

    def test_unknown_type_converted_to_string(self):
        class _Custom:
            def __str__(self):
                return "custom_value"

        result = json.loads(_serialize_context({"obj": _Custom()}))
        assert result["obj"] == "custom_value"

    def test_empty_dict_produces_empty_json_object(self):
        assert _serialize_context({}) == "{}"

    def test_nested_dict_preserved(self):
        ctx = {"outer": {"inner": 1}}
        result = json.loads(_serialize_context(ctx))
        assert result == ctx

    def test_fallback_to_empty_json_on_circular_reference(self):
        ctx: dict = {}
        ctx["self"] = ctx  # circular — json.dumps will raise
        result = _serialize_context(ctx)
        assert result == "{}"

    def test_context_not_silently_replaced_when_serializable(self):
        ctx = {"last_activity_days": 18, "risk_level": "high"}
        result = _serialize_context(ctx)
        assert "last_activity_days" in result
        assert "18" in result


# ===========================================================================
# record()
# ===========================================================================

class TestRecord:

    def test_returns_recommendation_instance(self):
        db = _make_db(existing=None)
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert isinstance(result, Recommendation)

    def test_row_has_correct_cbm_id(self):
        db = _make_db(existing=None)
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert result.cbm_id == 42

    def test_row_has_correct_recommendation_key(self):
        db = _make_db(existing=None)
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert result.recommendation_key == "attendance_outreach"

    def test_row_has_correct_recommendation_type(self):
        db = _make_db(existing=None)
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert result.recommendation_type == "reach_out"

    def test_context_stored_as_valid_json(self):
        db = _make_db(existing=None)
        result = _svc().record(db=db, **_BASE_KWARGS)
        parsed = json.loads(result.recommendation_context_json)
        assert parsed["last_activity_days"] == 18

    def test_context_not_null(self):
        db = _make_db(existing=None)
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert result.recommendation_context_json is not None
        assert result.recommendation_context_json != ""

    def test_is_active_defaults_true(self):
        db = _make_db(existing=None)
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert result.is_active is True

    def test_db_add_and_commit_called(self):
        db = _make_db(existing=None)
        _svc().record(db=db, **_BASE_KWARGS)
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_idempotent_returns_existing_row(self):
        existing = Recommendation(
            cbm_id=42,
            recommendation_key="attendance_outreach",
            is_active=True,
        )
        db = _make_db(existing=existing)
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert result is existing

    def test_idempotent_does_not_call_add(self):
        existing = Recommendation(
            cbm_id=42,
            recommendation_key="attendance_outreach",
            is_active=True,
        )
        db = _make_db(existing=existing)
        _svc().record(db=db, **_BASE_KWARGS)
        db.add.assert_not_called()

    def test_idempotent_does_not_call_commit(self):
        existing = Recommendation(
            cbm_id=42,
            recommendation_key="attendance_outreach",
            is_active=True,
        )
        db = _make_db(existing=existing)
        _svc().record(db=db, **_BASE_KWARGS)
        db.commit.assert_not_called()

    def test_inactive_row_does_not_block_new_insert(self):
        """is_active=False row is not returned by idempotency guard —
        the mock returns None (simulating no active row), so a new row is inserted."""
        db = _make_db(existing=None)
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert result is not None
        db.add.assert_called_once()

    def test_returns_none_on_db_error(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("connection lost")
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert result is None

    def test_rollback_called_on_db_error(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("connection lost")
        _svc().record(db=db, **_BASE_KWARGS)
        db.rollback.assert_called_once()

    def test_does_not_raise_on_db_error(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("connection lost")
        # Must not propagate
        _svc().record(db=db, **_BASE_KWARGS)

    def test_model_name_none_when_omitted(self):
        kwargs = {**_BASE_KWARGS}
        kwargs.pop("model_name")
        db = _make_db(existing=None)
        result = _svc().record(db=db, **kwargs)
        assert result.model_name is None

    def test_model_name_stored_when_provided(self):
        db = _make_db(existing=None)
        result = _svc().record(db=db, **_BASE_KWARGS)
        assert result.model_name == "claude-sonnet-4-6"


# ===========================================================================
# invalidate()
# ===========================================================================

class TestInvalidate:

    def _make_active_row(self) -> MagicMock:
        row = MagicMock(spec=Recommendation)
        row.is_active = True
        row.invalidated_at = None
        row.invalidation_reason = None
        return row

    def test_sets_is_active_false(self):
        row = self._make_active_row()
        db = _make_db(existing=row)
        _svc().invalidate(db=db, cbm_id=42, recommendation_key="attendance_outreach", reason="superseded")
        assert row.is_active is False

    def test_sets_invalidated_at(self):
        row = self._make_active_row()
        db = _make_db(existing=row)
        before = datetime.utcnow()
        _svc().invalidate(db=db, cbm_id=42, recommendation_key="attendance_outreach", reason="superseded")
        assert row.invalidated_at is not None
        assert row.invalidated_at >= before

    def test_stores_reason(self):
        row = self._make_active_row()
        db = _make_db(existing=row)
        _svc().invalidate(db=db, cbm_id=42, recommendation_key="attendance_outreach", reason="superseded by new assessment")
        assert row.invalidation_reason == "superseded by new assessment"

    def test_commits_after_update(self):
        row = self._make_active_row()
        db = _make_db(existing=row)
        _svc().invalidate(db=db, cbm_id=42, recommendation_key="attendance_outreach", reason="superseded")
        db.commit.assert_called_once()

    def test_noop_when_no_active_row(self):
        db = _make_db(existing=None)
        # Must not raise and must not commit
        _svc().invalidate(db=db, cbm_id=42, recommendation_key="attendance_outreach", reason="superseded")
        db.commit.assert_not_called()

    def test_does_not_raise_on_db_error(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("db gone")
        _svc().invalidate(db=db, cbm_id=42, recommendation_key="attendance_outreach", reason="superseded")

    def test_rollback_called_on_db_error(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("db gone")
        _svc().invalidate(db=db, cbm_id=42, recommendation_key="attendance_outreach", reason="superseded")
        db.rollback.assert_called_once()
