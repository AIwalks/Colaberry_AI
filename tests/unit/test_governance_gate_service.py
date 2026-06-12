"""Unit tests for GovernanceGateService.check_delivery_approved().

All tests are isolated — no real database session, no MSSQL, no SQLite.
The db session is a MagicMock that simulates query/filter/order_by/first chains.
AIInterpretation and GovernanceReview objects are built as SimpleNamespace stubs.

Directive: directives/governance_gate_contract.md
Contract: 7 fixed outcomes — approved_review, pending, rejected, deferred,
          no_governance_review, no_sentinel_data, gate_error.

Test classes:
  - TestApprovedPath             → approved_review
  - TestBlockedPaths             → pending, rejected, deferred
  - TestNoGovernanceReview       → no_governance_review
  - TestNoSentinelData           → no_sentinel_data (no active interpretation)
  - TestNoSentinelDataEdgeCases  → empty entity_id, invalidated interpretation only
  - TestFailOpen                 → gate_error on DB exception; logs at ERROR
  - TestReturnContract           → return dict shape always satisfies the contract
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.governance_gate_service import GovernanceGateService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENTITY_ID   = "101"
_ENTITY_TYPE = "student"
_INTERP_ID   = 42
_REVIEW_ID   = 77

SVC = GovernanceGateService()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_interpretation(
    id_val: int = _INTERP_ID,
    entity_id: str = _ENTITY_ID,
    entity_type: str = _ENTITY_TYPE,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id          = id_val,
        entity_id   = entity_id,
        entity_type = entity_type,
        is_active   = is_active,
    )


def _make_review(
    id_val: int = _REVIEW_ID,
    interpretation_id: int = _INTERP_ID,
    status: str = "pending",
) -> SimpleNamespace:
    return SimpleNamespace(
        id                = id_val,
        interpretation_id = interpretation_id,
        status            = status,
    )


def _make_db(
    interpretation: "SimpleNamespace | None" = None,
    review: "SimpleNamespace | None" = None,
) -> MagicMock:
    """Return a mock session whose query().filter().order_by().first() returns
    `interpretation` on the first query call and `review` on the second.

    The mock uses a call counter so the two sequential queries return
    different values as the service walks through Step 1 → Step 2.
    """
    db = MagicMock()
    call_order = {"n": 0}

    def _query_side_effect(_model):
        call_order["n"] += 1
        q = MagicMock()
        q.filter.return_value      = q
        q.order_by.return_value    = q
        q.limit.return_value       = q
        if call_order["n"] == 1:
            q.first.return_value = interpretation
        else:
            q.first.return_value = review
        return q

    db.query.side_effect = _query_side_effect
    return db


def _make_db_raises(exc: Exception) -> MagicMock:
    """Return a mock session whose first .query() call raises `exc`."""
    db = MagicMock()
    db.query.side_effect = exc
    return db


# ===========================================================================
# TestApprovedPath
# ===========================================================================

class TestApprovedPath:
    """Active interpretation + approved review → approved_review."""

    def _run(self):
        interp = _make_interpretation()
        review = _make_review(status="approved")
        db     = _make_db(interpretation=interp, review=review)
        return SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)

    def test_approved_is_true(self):
        result = self._run()
        assert result["approved"] is True

    def test_reason_is_approved_review(self):
        result = self._run()
        assert result["reason"] == "approved_review"

    def test_review_id_is_present_and_integer(self):
        result = self._run()
        assert isinstance(result["review_id"], int)

    def test_review_id_matches_review_row(self):
        result = self._run()
        assert result["review_id"] == _REVIEW_ID


# ===========================================================================
# TestBlockedPaths
# ===========================================================================

class TestBlockedPaths:
    """Active interpretation + non-approved review → blocked outcomes."""

    def _run(self, status: str):
        interp = _make_interpretation()
        review = _make_review(status=status)
        db     = _make_db(interpretation=interp, review=review)
        return SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)

    # --- pending ---

    def test_pending_approved_is_false(self):
        assert self._run("pending")["approved"] is False

    def test_pending_reason(self):
        assert self._run("pending")["reason"] == "pending"

    def test_pending_review_id_is_integer(self):
        assert isinstance(self._run("pending")["review_id"], int)

    # --- rejected ---

    def test_rejected_approved_is_false(self):
        assert self._run("rejected")["approved"] is False

    def test_rejected_reason(self):
        assert self._run("rejected")["reason"] == "rejected"

    def test_rejected_review_id_is_integer(self):
        assert isinstance(self._run("rejected")["review_id"], int)

    # --- deferred ---

    def test_deferred_approved_is_false(self):
        assert self._run("deferred")["approved"] is False

    def test_deferred_reason(self):
        assert self._run("deferred")["reason"] == "deferred"

    def test_deferred_review_id_is_integer(self):
        assert isinstance(self._run("deferred")["review_id"], int)


# ===========================================================================
# TestNoGovernanceReview
# ===========================================================================

class TestNoGovernanceReview:
    """Active interpretation exists but no GovernanceReview row → no_governance_review."""

    def _run(self):
        interp = _make_interpretation()
        db     = _make_db(interpretation=interp, review=None)
        return SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)

    def test_approved_is_false(self):
        assert self._run()["approved"] is False

    def test_reason_is_no_governance_review(self):
        assert self._run()["reason"] == "no_governance_review"

    def test_review_id_is_none(self):
        assert self._run()["review_id"] is None


# ===========================================================================
# TestNoSentinelData
# ===========================================================================

class TestNoSentinelData:
    """No active AIInterpretation exists → no_sentinel_data; delivery proceeds."""

    def _run(self, entity_id: str = _ENTITY_ID):
        db = _make_db(interpretation=None, review=None)
        return SVC.check_delivery_approved(db, entity_id, _ENTITY_TYPE)

    def test_approved_is_true(self):
        assert self._run()["approved"] is True

    def test_reason_is_no_sentinel_data(self):
        assert self._run()["reason"] == "no_sentinel_data"

    def test_review_id_is_none(self):
        assert self._run()["review_id"] is None

    def test_governance_review_not_queried_when_no_interpretation(self):
        """Step 2 query must not be issued when Step 1 returns no row."""
        db = _make_db(interpretation=None, review=None)
        SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)
        assert db.query.call_count == 1, (
            "GovernanceReview query must not be issued when AIInterpretation is missing"
        )


# ===========================================================================
# TestNoSentinelDataEdgeCases
# ===========================================================================

class TestNoSentinelDataEdgeCases:
    """Edge cases that must still return no_sentinel_data."""

    def test_empty_entity_id_returns_no_sentinel_data(self):
        db     = _make_db(interpretation=None, review=None)
        result = SVC.check_delivery_approved(db, "", _ENTITY_TYPE)
        assert result["approved"] is True
        assert result["reason"]   == "no_sentinel_data"
        assert result["review_id"] is None

    def test_empty_entity_id_does_not_raise(self):
        db = _make_db(interpretation=None, review=None)
        try:
            SVC.check_delivery_approved(db, "", _ENTITY_TYPE)
        except Exception as exc:
            pytest.fail(f"check_delivery_approved raised unexpectedly: {exc}")

    def test_invalidated_interpretation_only_returns_no_sentinel_data(self):
        """An interpretation with is_active=False must not be matched by the query.
        The mock simulates this by returning None (i.e., the query filters it out).
        """
        db     = _make_db(interpretation=None, review=None)
        result = SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["approved"] is True
        assert result["reason"]   == "no_sentinel_data"


# ===========================================================================
# TestFailOpen
# ===========================================================================

class TestFailOpen:
    """Any DB exception → gate_error; approved=True; exception logged at ERROR."""

    def _run(self, exc=None):
        exc = exc or RuntimeError("DB connection lost")
        db  = _make_db_raises(exc)
        return SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)

    def test_approved_is_true_on_exception(self):
        assert self._run()["approved"] is True

    def test_reason_is_gate_error_on_exception(self):
        assert self._run()["reason"] == "gate_error"

    def test_review_id_is_none_on_exception(self):
        assert self._run()["review_id"] is None

    def test_does_not_raise_on_db_exception(self):
        db = _make_db_raises(RuntimeError("simulated failure"))
        try:
            SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)
        except Exception as exc:
            pytest.fail(f"check_delivery_approved must not propagate exceptions: {exc}")

    def test_logs_at_error_level_on_exception(self):
        """The gate must emit a logger.error() call containing the entity_id."""
        with patch("services.governance_gate_service.logger") as mock_logger:
            db = _make_db_raises(RuntimeError("timeout"))
            SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)

        mock_logger.error.assert_called_once()
        log_call = mock_logger.error.call_args
        log_args = log_call.args
        assert any(_ENTITY_ID in str(a) for a in log_args), (
            "ERROR log must include the entity_id so gate errors are traceable"
        )

    def test_sqlalchemy_error_handled_as_gate_error(self):
        """SQLAlchemy OperationalError must be caught and return gate_error."""
        from unittest.mock import MagicMock as MM
        exc = Exception("OperationalError: no such table")
        db  = _make_db_raises(exc)
        result = SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["reason"] == "gate_error"

    def test_gate_error_approved_true_preserves_delivery_pipeline(self):
        """fail-open: gate_error must never block delivery (approved must be True)."""
        result = self._run(exc=ConnectionError("DB unreachable"))
        assert result["approved"] is True, (
            "fail-open policy requires approved=True on gate_error — "
            "the monitoring layer must not become a single point of failure"
        )


# ===========================================================================
# TestReturnContract
# ===========================================================================

class TestReturnContract:
    """Return value must always be a dict with approved, reason, review_id."""

    CASES = [
        # (interpretation, review, label)
        ("active_approved",          True,  "approved"),
        ("active_pending",           True,  "pending"),
        ("active_rejected",          True,  "rejected"),
        ("active_deferred",          True,  "deferred"),
        ("active_no_review",         True,  None),
        ("no_interpretation",        False, None),
    ]

    def _result_for(self, has_interp: bool, review_status: "str | None") -> dict:
        interp = _make_interpretation() if has_interp else None
        review = _make_review(status=review_status) if review_status else None
        db     = _make_db(interpretation=interp, review=review)
        return SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)

    def test_return_is_dict_approved_review(self):
        assert isinstance(self._result_for(True, "approved"), dict)

    def test_return_is_dict_pending(self):
        assert isinstance(self._result_for(True, "pending"), dict)

    def test_return_is_dict_rejected(self):
        assert isinstance(self._result_for(True, "rejected"), dict)

    def test_return_is_dict_deferred(self):
        assert isinstance(self._result_for(True, "deferred"), dict)

    def test_return_is_dict_no_review(self):
        assert isinstance(self._result_for(True, None), dict)

    def test_return_is_dict_no_sentinel_data(self):
        assert isinstance(self._result_for(False, None), dict)

    def test_return_is_dict_gate_error(self):
        db = _make_db_raises(RuntimeError("x"))
        assert isinstance(SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE), dict)

    def test_approved_key_always_present_approved_review(self):
        result = self._result_for(True, "approved")
        assert "approved" in result

    def test_approved_key_always_present_no_sentinel_data(self):
        result = self._result_for(False, None)
        assert "approved" in result

    def test_approved_key_always_present_gate_error(self):
        db = _make_db_raises(RuntimeError("x"))
        result = SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)
        assert "approved" in result

    def test_reason_is_always_str_approved_review(self):
        assert isinstance(self._result_for(True, "approved")["reason"], str)

    def test_reason_is_always_str_no_sentinel_data(self):
        assert isinstance(self._result_for(False, None)["reason"], str)

    def test_reason_is_always_str_gate_error(self):
        db = _make_db_raises(RuntimeError("x"))
        result = SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)
        assert isinstance(result["reason"], str)

    def test_review_id_key_always_present_approved_review(self):
        assert "review_id" in self._result_for(True, "approved")

    def test_review_id_key_always_present_no_sentinel_data(self):
        assert "review_id" in self._result_for(False, None)

    def test_review_id_key_always_present_gate_error(self):
        db = _make_db_raises(RuntimeError("x"))
        result = SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)
        assert "review_id" in result

    def test_review_id_is_int_or_none_approved_review(self):
        review_id = self._result_for(True, "approved")["review_id"]
        assert isinstance(review_id, int) or review_id is None

    def test_review_id_is_none_no_sentinel_data(self):
        assert self._result_for(False, None)["review_id"] is None

    def test_review_id_is_none_gate_error(self):
        db = _make_db_raises(RuntimeError("x"))
        result = SVC.check_delivery_approved(db, _ENTITY_ID, _ENTITY_TYPE)
        assert result["review_id"] is None

    def test_approved_value_is_bool_not_truthy(self):
        for has_interp, review_status in [
            (True,  "approved"),
            (True,  "pending"),
            (False, None),
        ]:
            result = self._result_for(has_interp, review_status)
            assert isinstance(result["approved"], bool), (
                f"approved must be a bool, got {type(result['approved'])}"
            )
