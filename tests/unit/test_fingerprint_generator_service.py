"""Unit tests for FingerprintGeneratorService — no DB required for rule tests."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.fingerprint_generator_service import (
    FingerprintGeneratorService,
    _evaluate_rules,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENTITY_ID   = "42"
_ENTITY_TYPE = "student"


def _make_extraction(
    last_login_days=None,
    last_activity_days=None,
    is_class_active=None,
    active_status=None,
    trigger_completion_rate=None,
    total_triggers_fired=None,
) -> dict:
    return {
        "dimensions": {
            "engagement": {
                "signals": [
                    {"name": "last_login_days",    "value": last_login_days,    "unit": "days"},
                    {"name": "last_activity_days", "value": last_activity_days, "unit": "days"},
                    {"name": "is_class_active",    "value": is_class_active,    "unit": "bool"},
                    {"name": "active_status",      "value": active_status,      "unit": "string"},
                ],
                "fingerprints": [],
            },
            "communication_responsiveness": {
                "signals": [
                    {"name": "trigger_completion_rate", "value": trigger_completion_rate, "unit": "ratio"},
                    {"name": "total_triggers_fired",    "value": total_triggers_fired,    "unit": "count"},
                ],
                "fingerprints": [],
            },
        }
    }


def _make_db_mock(duplicate: bool = False):
    db = MagicMock()
    scalar_mock = MagicMock(return_value=1 if duplicate else 0)
    db.query.return_value.filter.return_value.scalar = scalar_mock

    fake_record = SimpleNamespace(id=99)
    db.refresh.side_effect = lambda rec: setattr(rec, "id", 99)
    return db


# ===========================================================================
# _flatten_signals
# ===========================================================================

class TestFlattenSignals:

    def test_basic_flattening(self):
        extraction = _make_extraction(last_login_days=10)
        svc = FingerprintGeneratorService()
        flat = svc._flatten_signals(extraction)
        assert flat["last_login_days"] == 10

    def test_none_values_included(self):
        extraction = _make_extraction()
        svc = FingerprintGeneratorService()
        flat = svc._flatten_signals(extraction)
        assert "last_login_days" in flat
        assert flat["last_login_days"] is None

    def test_all_dimensions_merged(self):
        extraction = _make_extraction(
            last_activity_days=20,
            trigger_completion_rate=0.1,
        )
        svc = FingerprintGeneratorService()
        flat = svc._flatten_signals(extraction)
        assert flat["last_activity_days"] == 20
        assert flat["trigger_completion_rate"] == 0.1

    def test_empty_extraction_returns_empty_dict(self):
        svc = FingerprintGeneratorService()
        assert svc._flatten_signals({}) == {}

    def test_dimension_with_no_signals_skipped(self):
        extraction = {"dimensions": {"engagement": {"signals": []}}}
        svc = FingerprintGeneratorService()
        assert svc._flatten_signals(extraction) == {}


# ===========================================================================
# _evaluate_rules — stale_login_pattern
# ===========================================================================

class TestStaleLoginRule:

    def test_fires_at_threshold(self):
        signals = {"last_login_days": 14}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        names = [r["pattern_name"] for r in results]
        assert "stale_login_pattern" in names

    def test_does_not_fire_below_threshold(self):
        signals = {"last_login_days": 13}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        names = [r["pattern_name"] for r in results]
        assert "stale_login_pattern" not in names

    def test_does_not_fire_on_none(self):
        signals = {"last_login_days": None}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        assert not any(r["pattern_name"] == "stale_login_pattern" for r in results)

    def test_risk_medium_at_exactly_14(self):
        signals = {"last_login_days": 14}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        match = next(r for r in results if r["pattern_name"] == "stale_login_pattern")
        assert match["risk_level"] == "medium"

    def test_risk_high_at_21(self):
        signals = {"last_login_days": 21}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        match = next(r for r in results if r["pattern_name"] == "stale_login_pattern")
        assert match["risk_level"] == "high"

    def test_score_capped_at_1(self):
        signals = {"last_login_days": 60}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        match = next(r for r in results if r["pattern_name"] == "stale_login_pattern")
        assert match["score"] == 1.0

    def test_score_proportional(self):
        signals = {"last_login_days": 15}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        match = next(r for r in results if r["pattern_name"] == "stale_login_pattern")
        assert abs(match["score"] - 15 / 30.0) < 1e-9


# ===========================================================================
# _evaluate_rules — stale_activity_pattern
# ===========================================================================

class TestStaleActivityRule:

    def test_fires_at_threshold(self):
        signals = {"last_activity_days": 14}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        assert any(r["pattern_name"] == "stale_activity_pattern" for r in results)

    def test_does_not_fire_below_threshold(self):
        signals = {"last_activity_days": 13}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        assert not any(r["pattern_name"] == "stale_activity_pattern" for r in results)

    def test_risk_high_at_21(self):
        signals = {"last_activity_days": 21}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        match = next(r for r in results if r["pattern_name"] == "stale_activity_pattern")
        assert match["risk_level"] == "high"

    def test_details_json_contains_threshold(self):
        signals = {"last_activity_days": 20}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        match = next(r for r in results if r["pattern_name"] == "stale_activity_pattern")
        details = json.loads(match["details_json"])
        assert details["threshold"] == 14
        assert details["last_activity_days"] == 20


# ===========================================================================
# _evaluate_rules — low_trigger_completion
# ===========================================================================

class TestLowTriggerCompletionRule:

    def test_fires_when_all_conditions_met(self):
        signals = {"trigger_completion_rate": 0.1, "total_triggers_fired": 5}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        assert any(r["pattern_name"] == "low_trigger_completion" for r in results)

    def test_does_not_fire_when_rate_above_threshold(self):
        signals = {"trigger_completion_rate": 0.30, "total_triggers_fired": 5}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        assert not any(r["pattern_name"] == "low_trigger_completion" for r in results)

    def test_does_not_fire_when_too_few_triggers(self):
        signals = {"trigger_completion_rate": 0.1, "total_triggers_fired": 2}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        assert not any(r["pattern_name"] == "low_trigger_completion" for r in results)

    def test_does_not_fire_when_rate_none(self):
        signals = {"trigger_completion_rate": None, "total_triggers_fired": 5}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        assert not any(r["pattern_name"] == "low_trigger_completion" for r in results)

    def test_fires_at_exact_minimum_triggers(self):
        signals = {"trigger_completion_rate": 0.24, "total_triggers_fired": 3}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        assert any(r["pattern_name"] == "low_trigger_completion" for r in results)

    def test_risk_always_high(self):
        signals = {"trigger_completion_rate": 0.1, "total_triggers_fired": 5}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        match = next(r for r in results if r["pattern_name"] == "low_trigger_completion")
        assert match["risk_level"] == "high"

    def test_score_is_one_minus_rate(self):
        signals = {"trigger_completion_rate": 0.1, "total_triggers_fired": 5}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        match = next(r for r in results if r["pattern_name"] == "low_trigger_completion")
        assert abs(match["score"] - 0.9) < 1e-9


# ===========================================================================
# _evaluate_rules — active_but_disconnected
# ===========================================================================

class TestActiveButDisconnectedRule:

    def _signals(self, active_status="Active", is_class_active=1, days=20):
        return {
            "last_activity_days": days,
            "is_class_active":    is_class_active,
            "active_status":      active_status,
        }

    def test_fires_when_all_conditions_met(self):
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, self._signals())
        assert any(r["pattern_name"] == "active_but_disconnected" for r in results)

    def test_fires_with_active_status_y(self):
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, self._signals(active_status="Y"))
        assert any(r["pattern_name"] == "active_but_disconnected" for r in results)

    def test_fires_with_active_status_a(self):
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, self._signals(active_status="A"))
        assert any(r["pattern_name"] == "active_but_disconnected" for r in results)

    def test_case_insensitive_active_status(self):
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, self._signals(active_status="active"))
        assert any(r["pattern_name"] == "active_but_disconnected" for r in results)

    def test_does_not_fire_when_class_inactive(self):
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, self._signals(is_class_active=0))
        assert not any(r["pattern_name"] == "active_but_disconnected" for r in results)

    def test_does_not_fire_when_activity_days_below_threshold(self):
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, self._signals(days=13))
        assert not any(r["pattern_name"] == "active_but_disconnected" for r in results)

    def test_does_not_fire_when_status_inactive(self):
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, self._signals(active_status="Inactive"))
        assert not any(r["pattern_name"] == "active_but_disconnected" for r in results)

    def test_risk_always_high(self):
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, self._signals())
        match = next(r for r in results if r["pattern_name"] == "active_but_disconnected")
        assert match["risk_level"] == "high"


# ===========================================================================
# _evaluate_rules — multiple rules can fire simultaneously
# ===========================================================================

class TestMultipleRulesFire:

    def test_both_stale_patterns_can_fire(self):
        signals = {"last_login_days": 20, "last_activity_days": 20}
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        names = [r["pattern_name"] for r in results]
        assert "stale_login_pattern" in names
        assert "stale_activity_pattern" in names

    def test_no_rules_fire_when_no_signals(self):
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, {})
        assert results == []

    def test_three_rules_fire(self):
        signals = {
            "last_login_days":          20,
            "last_activity_days":       20,
            "is_class_active":          1,
            "active_status":            "Active",
            "trigger_completion_rate":  0.1,
            "total_triggers_fired":     5,
        }
        results = _evaluate_rules(_ENTITY_ID, _ENTITY_TYPE, signals)
        names = [r["pattern_name"] for r in results]
        assert len(results) == 4  # all 4 rules fire


# ===========================================================================
# _is_recent_duplicate
# ===========================================================================

class TestIsRecentDuplicate:

    def test_returns_true_when_count_is_positive(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = 1
        svc = FingerprintGeneratorService()
        assert svc._is_recent_duplicate(db, "42", "student", "stale_login_pattern") is True

    def test_returns_false_when_count_is_zero(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = 0
        svc = FingerprintGeneratorService()
        assert svc._is_recent_duplicate(db, "42", "student", "stale_login_pattern") is False

    def test_returns_false_when_scalar_is_none(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = None
        svc = FingerprintGeneratorService()
        assert svc._is_recent_duplicate(db, "42", "student", "stale_login_pattern") is False


# ===========================================================================
# generate_and_persist — integration of rule + dedup + DB write
# ===========================================================================

class TestGenerateAndPersist:

    def _svc_with_no_duplicates(self):
        svc = FingerprintGeneratorService()
        svc._is_recent_duplicate = MagicMock(return_value=False)
        return svc

    def _svc_with_all_duplicates(self):
        svc = FingerprintGeneratorService()
        svc._is_recent_duplicate = MagicMock(return_value=True)
        return svc

    def _db_mock(self):
        db = MagicMock()
        call_count = [0]

        def fake_refresh(record):
            call_count[0] += 1
            record.id = call_count[0]

        db.refresh.side_effect = fake_refresh
        return db

    def test_returns_empty_when_no_rules_fire(self):
        svc = self._svc_with_no_duplicates()
        extraction = _make_extraction()  # all None signals
        result = svc.generate_and_persist(MagicMock(), _ENTITY_ID, _ENTITY_TYPE, extraction)
        assert result == []

    def test_returns_written_record_when_rule_fires(self):
        svc = self._svc_with_no_duplicates()
        db  = self._db_mock()
        extraction = _make_extraction(last_login_days=20)
        result = svc.generate_and_persist(db, _ENTITY_ID, _ENTITY_TYPE, extraction)
        assert len(result) == 1
        assert result[0]["pattern_name"] == "stale_login_pattern"

    def test_result_contains_expected_keys(self):
        svc = self._svc_with_no_duplicates()
        db  = self._db_mock()
        extraction = _make_extraction(last_login_days=20)
        result = svc.generate_and_persist(db, _ENTITY_ID, _ENTITY_TYPE, extraction)
        assert set(result[0].keys()) == {"id", "pattern_name", "score", "risk_level", "details_json"}

    def test_db_add_and_commit_called_for_each_written_record(self):
        svc = self._svc_with_no_duplicates()
        db  = self._db_mock()
        extraction = _make_extraction(last_login_days=20, last_activity_days=20)
        svc.generate_and_persist(db, _ENTITY_ID, _ENTITY_TYPE, extraction)
        assert db.add.call_count == 2
        assert db.commit.call_count == 2

    def test_skips_duplicates_and_returns_empty(self):
        svc = self._svc_with_all_duplicates()
        db  = self._db_mock()
        extraction = _make_extraction(last_login_days=20)
        result = svc.generate_and_persist(db, _ENTITY_ID, _ENTITY_TYPE, extraction)
        assert result == []
        db.add.assert_not_called()

    def test_db_error_handled_gracefully(self):
        svc = self._svc_with_no_duplicates()
        db  = MagicMock()
        db.commit.side_effect = Exception("DB connection lost")
        extraction = _make_extraction(last_login_days=20)
        result = svc.generate_and_persist(db, _ENTITY_ID, _ENTITY_TYPE, extraction)
        assert result == []
        db.rollback.assert_called()

    def test_partial_failure_returns_successful_writes(self):
        """First pattern succeeds; second pattern's commit raises — only first returned."""
        svc = self._svc_with_no_duplicates()
        db  = MagicMock()
        commit_calls = [0]

        def side_effect_commit():
            commit_calls[0] += 1
            if commit_calls[0] == 2:
                raise Exception("DB error on second write")

        db.commit.side_effect = side_effect_commit
        db.refresh.side_effect = lambda rec: setattr(rec, "id", commit_calls[0])
        extraction = _make_extraction(last_login_days=20, last_activity_days=20)
        result = svc.generate_and_persist(db, _ENTITY_ID, _ENTITY_TYPE, extraction)
        assert len(result) == 1
