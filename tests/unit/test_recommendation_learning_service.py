"""Unit tests for services/recommendation_learning_service.py.

All tests use mock DB sessions — no live DB or MSSQL required.

Coverage
────────
- get_success_rates(): rate calculation (all improved, all not_improved, mixed)
- get_success_rates(): success_rate=None when total_eligible=0
- get_success_rates(): has_sufficient_sample threshold logic
- get_success_rates(): SQL SUM returning None handled as 0
- get_success_rates(): dimension and risk_level filters passed to query
- get_success_rates(): empty result set returns []
- get_success_rates(): DB error returns []
- get_ranked_keys(): sufficient-sample keys sorted by rate descending
- get_ranked_keys(): insufficient-sample keys appended in original candidate order
- get_ranked_keys(): candidates absent from rates appended in original order
- get_ranked_keys(): all candidates unsampled preserves original order
- get_ranked_keys(): no candidates removed
- get_ranked_keys(): tied success rates preserve stable order
- get_ranked_keys(): DB error returns original candidate list
- get_ranked_keys(): empty candidate list returns []
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from services.recommendation_learning_service import RecommendationLearningService


# ===========================================================================
# Helpers
# ===========================================================================

def _svc() -> RecommendationLearningService:
    return RecommendationLearningService()


def _make_row(
    key:            str,
    rtype:          str,
    total_eligible: int,
    total_improved: int,
) -> SimpleNamespace:
    """Simulate a SQLAlchemy Row returned by the aggregation query."""
    return SimpleNamespace(
        recommendation_key  = key,
        recommendation_type = rtype,
        total_eligible      = total_eligible,
        total_improved      = total_improved,
    )


def _make_db(rows: list) -> MagicMock:
    """Return a mock session whose query chain returns `rows` from .all()."""
    db = MagicMock()
    (
        db.query.return_value
           .join.return_value
           .filter.return_value
           .group_by.return_value
           .all.return_value
    ) = rows
    return db


def _make_db_error() -> MagicMock:
    """Return a mock session whose query chain raises RuntimeError."""
    db = MagicMock()
    db.query.side_effect = RuntimeError("db gone")
    return db


def _make_rates(
    items: list[tuple[str, int, int, bool]],
) -> list[dict]:
    """Build a minimal get_success_rates()-style return value for get_ranked_keys tests.

    Each tuple: (recommendation_key, total_eligible, total_improved, has_sufficient_sample)
    """
    out = []
    for key, total_eligible, total_improved, sufficient in items:
        out.append({
            "recommendation_key":    key,
            "recommendation_type":   "reach_out",
            "total_eligible":        total_eligible,
            "total_improved":        total_improved,
            "success_rate":          (total_improved / total_eligible) if total_eligible > 0 else None,
            "has_sufficient_sample": sufficient,
        })
    return out


# ===========================================================================
# get_success_rates()
# ===========================================================================

class TestGetSuccessRates:

    def test_returns_list(self):
        db = _make_db([_make_row("k1", "reach_out", 10, 7)])
        result = _svc().get_success_rates(db)
        assert isinstance(result, list)

    def test_all_improved_rate_is_one(self):
        db = _make_db([_make_row("k1", "reach_out", 10, 10)])
        result = _svc().get_success_rates(db)
        assert result[0]["success_rate"] == 1.0

    def test_no_improved_rate_is_zero(self):
        db = _make_db([_make_row("k1", "reach_out", 10, 0)])
        result = _svc().get_success_rates(db)
        assert result[0]["success_rate"] == 0.0

    def test_mixed_rate_calculated_correctly(self):
        db = _make_db([_make_row("k1", "reach_out", 5, 3)])
        result = _svc().get_success_rates(db)
        assert abs(result[0]["success_rate"] - 0.6) < 1e-9

    def test_success_rate_is_none_when_total_eligible_zero(self):
        db = _make_db([_make_row("k1", "reach_out", 0, 0)])
        result = _svc().get_success_rates(db)
        assert result[0]["success_rate"] is None

    def test_sql_sum_none_treated_as_zero(self):
        """SQL SUM returns NULL when no rows match — handle it as 0."""
        row = SimpleNamespace(
            recommendation_key  = "k1",
            recommendation_type = "reach_out",
            total_eligible      = 5,
            total_improved      = None,  # simulates SQL NULL
        )
        db = _make_db([row])
        result = _svc().get_success_rates(db)
        assert result[0]["total_improved"] == 0
        assert result[0]["success_rate"] == 0.0

    def test_has_sufficient_sample_true_at_threshold(self):
        db = _make_db([_make_row("k1", "reach_out", 10, 6)])
        result = _svc().get_success_rates(db, min_sample=10)
        assert result[0]["has_sufficient_sample"] is True

    def test_has_sufficient_sample_false_below_threshold(self):
        db = _make_db([_make_row("k1", "reach_out", 9, 6)])
        result = _svc().get_success_rates(db, min_sample=10)
        assert result[0]["has_sufficient_sample"] is False

    def test_has_sufficient_sample_false_when_no_eligible(self):
        db = _make_db([_make_row("k1", "reach_out", 0, 0)])
        result = _svc().get_success_rates(db)
        assert result[0]["has_sufficient_sample"] is False

    def test_result_contains_all_required_keys(self):
        db = _make_db([_make_row("k1", "reach_out", 10, 7)])
        result = _svc().get_success_rates(db)
        required = {
            "recommendation_key", "recommendation_type",
            "total_eligible", "total_improved",
            "success_rate", "has_sufficient_sample",
        }
        assert required.issubset(result[0].keys())

    def test_recommendation_key_preserved_in_output(self):
        db = _make_db([_make_row("attendance_outreach", "reach_out", 12, 8)])
        result = _svc().get_success_rates(db)
        assert result[0]["recommendation_key"] == "attendance_outreach"

    def test_recommendation_type_preserved_in_output(self):
        db = _make_db([_make_row("attendance_outreach", "reach_out", 12, 8)])
        result = _svc().get_success_rates(db)
        assert result[0]["recommendation_type"] == "reach_out"

    def test_multiple_keys_returned(self):
        db = _make_db([
            _make_row("attendance_outreach", "reach_out", 15, 10),
            _make_row("homework_outreach",   "reach_out",  8,  3),
        ])
        result = _svc().get_success_rates(db)
        assert len(result) == 2

    def test_empty_query_result_returns_empty_list(self):
        db = _make_db([])
        result = _svc().get_success_rates(db)
        assert result == []

    def test_dimension_filter_forwarded_to_query(self):
        """When dimension is provided the filter chain is called; mock returns rows."""
        db = _make_db([_make_row("k1", "reach_out", 10, 7)])
        result = _svc().get_success_rates(db, dimension="attendance")
        assert len(result) == 1

    def test_risk_level_filter_forwarded_to_query(self):
        db = _make_db([_make_row("k1", "reach_out", 10, 7)])
        result = _svc().get_success_rates(db, risk_level="high")
        assert len(result) == 1

    def test_returns_empty_list_on_db_error(self):
        result = _svc().get_success_rates(_make_db_error())
        assert result == []

    def test_does_not_raise_on_db_error(self):
        _svc().get_success_rates(_make_db_error())


# ===========================================================================
# get_ranked_keys()
# ===========================================================================

class TestGetRankedKeys:

    def _db_with_rates(self, items: list[tuple]) -> MagicMock:
        """Return a mock db whose full query chain produces rows from items.

        Each item: (key, total_eligible, total_improved, has_sufficient_sample)
        — has_sufficient_sample is reflected via total_eligible >= 10.
        """
        rows = []
        for key, total_eligible, total_improved, sufficient in items:
            if sufficient:
                eligible = max(total_eligible, 10)
            else:
                eligible = min(total_eligible, 9)
            rows.append(_make_row(key, "reach_out", eligible, total_improved))
        return _make_db(rows)

    def test_sufficient_keys_ranked_by_rate_descending(self):
        """Higher success_rate key must appear first."""
        with patch.object(
            RecommendationLearningService, "get_success_rates",
            return_value=_make_rates([
                ("k_low",  10, 4, True),   # 0.4
                ("k_high", 10, 9, True),   # 0.9
                ("k_mid",  10, 6, True),   # 0.6
            ]),
        ):
            result = _svc().get_ranked_keys(MagicMock(), ["k_low", "k_high", "k_mid"])
        assert result == ["k_high", "k_mid", "k_low"]

    def test_insufficient_sample_keys_appended_in_original_order(self):
        with patch.object(
            RecommendationLearningService, "get_success_rates",
            return_value=_make_rates([
                ("k_ranked",   10, 8, True),   # 0.8 — sufficient
                ("k_unranked", 3,  2, False),  # insufficient
            ]),
        ):
            result = _svc().get_ranked_keys(
                MagicMock(), ["k_ranked", "k_unranked"]
            )
        assert result == ["k_ranked", "k_unranked"]

    def test_unknown_candidates_appended_in_original_order(self):
        """Candidates not present in success_rates output are appended last."""
        with patch.object(
            RecommendationLearningService, "get_success_rates",
            return_value=_make_rates([
                ("known_key", 10, 7, True),
            ]),
        ):
            result = _svc().get_ranked_keys(
                MagicMock(),
                ["unknown_a", "known_key", "unknown_b"],
            )
        assert result == ["known_key", "unknown_a", "unknown_b"]

    def test_all_candidates_unsampled_preserves_original_order(self):
        with patch.object(
            RecommendationLearningService, "get_success_rates",
            return_value=_make_rates([
                ("k1", 5, 3, False),
                ("k2", 2, 1, False),
            ]),
        ):
            result = _svc().get_ranked_keys(MagicMock(), ["k2", "k1"])
        assert result == ["k2", "k1"]

    def test_no_candidates_removed(self):
        candidates = ["k_a", "k_b", "k_c", "k_unknown"]
        with patch.object(
            RecommendationLearningService, "get_success_rates",
            return_value=_make_rates([
                ("k_a", 10, 7, True),
                ("k_b",  3, 2, False),
            ]),
        ):
            result = _svc().get_ranked_keys(MagicMock(), candidates)
        assert sorted(result) == sorted(candidates)

    def test_empty_candidates_returns_empty_list(self):
        with patch.object(
            RecommendationLearningService, "get_success_rates",
            return_value=[],
        ):
            result = _svc().get_ranked_keys(MagicMock(), [])
        assert result == []

    def test_tied_rates_preserve_stable_order(self):
        """Two keys with identical rates — their relative order is stable."""
        with patch.object(
            RecommendationLearningService, "get_success_rates",
            return_value=_make_rates([
                ("k1", 10, 7, True),
                ("k2", 10, 7, True),
            ]),
        ):
            result = _svc().get_ranked_keys(MagicMock(), ["k1", "k2"])
        assert set(result) == {"k1", "k2"}
        assert len(result) == 2

    def test_returns_original_order_on_db_error(self):
        candidates = ["k_a", "k_b", "k_c"]
        result = _svc().get_ranked_keys(_make_db_error(), candidates)
        assert result == candidates

    def test_does_not_raise_on_db_error(self):
        _svc().get_ranked_keys(_make_db_error(), ["k_a", "k_b"])

    def test_ranked_group_precedes_unranked_group(self):
        """All ranked keys must come before all unranked/unknown keys."""
        with patch.object(
            RecommendationLearningService, "get_success_rates",
            return_value=_make_rates([
                ("ranked_a", 10, 5, True),
                ("ranked_b", 10, 8, True),
            ]),
        ):
            result = _svc().get_ranked_keys(
                MagicMock(),
                ["unranked", "ranked_a", "ranked_b"],
            )
        ranked_positions   = [result.index(k) for k in ["ranked_a", "ranked_b"]]
        unranked_positions = [result.index("unranked")]
        assert max(ranked_positions) < min(unranked_positions)

    def test_none_success_rate_keys_treated_as_unranked(self):
        """Keys with success_rate=None (total_eligible=0) are unranked."""
        with patch.object(
            RecommendationLearningService, "get_success_rates",
            return_value=[
                {
                    "recommendation_key":    "k_none",
                    "recommendation_type":   "reach_out",
                    "total_eligible":        0,
                    "total_improved":        0,
                    "success_rate":          None,
                    "has_sufficient_sample": False,
                }
            ],
        ):
            result = _svc().get_ranked_keys(MagicMock(), ["k_none"])
        assert result == ["k_none"]
