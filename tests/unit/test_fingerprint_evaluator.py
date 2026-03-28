"""Unit tests for FingerprintEvaluator — pure scoring logic, no DB required."""

from core.fingerprint.patterns import BehaviorPattern
from core.fingerprint.evaluator import FingerprintEvaluator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pattern(thresholds: dict) -> BehaviorPattern:
    return BehaviorPattern(
        name="test_pattern",
        description="test",
        thresholds=thresholds,
    )


# ---------------------------------------------------------------------------
# All thresholds met — numeric
# ---------------------------------------------------------------------------

def test_all_numeric_thresholds_met_score_is_1():
    pattern = make_pattern({"logins": 5, "sessions": 3})
    result = FingerprintEvaluator().evaluate(pattern, {"logins": 10, "sessions": 5})
    assert result.score == 1.0


def test_all_numeric_thresholds_met_risk_is_high():
    pattern = make_pattern({"logins": 5, "sessions": 3})
    result = FingerprintEvaluator().evaluate(pattern, {"logins": 10, "sessions": 5})
    assert result.risk_level == "high"


def test_exact_threshold_value_counts_as_met():
    """actual >= expected — equality must count as met."""
    pattern = make_pattern({"logins": 5})
    result = FingerprintEvaluator().evaluate(pattern, {"logins": 5})
    assert result.score == 1.0
    assert result.risk_level == "high"


# ---------------------------------------------------------------------------
# No thresholds met — numeric
# ---------------------------------------------------------------------------

def test_no_numeric_thresholds_met_score_is_0():
    pattern = make_pattern({"logins": 10, "sessions": 8})
    result = FingerprintEvaluator().evaluate(pattern, {"logins": 1, "sessions": 1})
    assert result.score == 0.0


def test_no_thresholds_met_risk_is_low():
    pattern = make_pattern({"logins": 10, "sessions": 8})
    result = FingerprintEvaluator().evaluate(pattern, {"logins": 1, "sessions": 1})
    assert result.risk_level == "low"


# ---------------------------------------------------------------------------
# Partial match — medium risk
# ---------------------------------------------------------------------------

def test_half_thresholds_met_risk_is_medium():
    """2 of 4 met = score 0.5 → medium."""
    pattern = make_pattern({"a": 5, "b": 5, "c": 5, "d": 5})
    metrics = {"a": 10, "b": 10, "c": 1, "d": 1}
    result = FingerprintEvaluator().evaluate(pattern, metrics)
    assert result.score == 0.5
    assert result.risk_level == "medium"


def test_three_of_four_met_score_is_0_75_risk_is_medium():
    """3 of 4 = score 0.75 → medium (< 0.8 threshold for high)."""
    pattern = make_pattern({"a": 5, "b": 5, "c": 5, "d": 5})
    metrics = {"a": 10, "b": 10, "c": 10, "d": 1}
    result = FingerprintEvaluator().evaluate(pattern, metrics)
    assert result.score == 0.75
    assert result.risk_level == "medium"


def test_score_0_8_exactly_is_high_not_medium():
    """Boundary: score >= 0.8 is high."""
    pattern = make_pattern({"a": 1, "b": 1, "c": 1, "d": 1, "e": 1})
    metrics = {"a": 1, "b": 1, "c": 1, "d": 1, "e": 0}  # 4 of 5 = 0.8
    result = FingerprintEvaluator().evaluate(pattern, metrics)
    assert result.score == 0.8
    assert result.risk_level == "high"


# ---------------------------------------------------------------------------
# Empty thresholds
# ---------------------------------------------------------------------------

def test_empty_thresholds_score_is_0():
    pattern = make_pattern({})
    result = FingerprintEvaluator().evaluate(pattern, {"logins": 10})
    assert result.score == 0.0


def test_empty_thresholds_risk_is_low():
    pattern = make_pattern({})
    result = FingerprintEvaluator().evaluate(pattern, {"logins": 10})
    assert result.risk_level == "low"


def test_empty_thresholds_and_empty_metrics_score_is_0():
    pattern = make_pattern({})
    result = FingerprintEvaluator().evaluate(pattern, {})
    assert result.score == 0.0


# ---------------------------------------------------------------------------
# Non-numeric thresholds — exact match
# ---------------------------------------------------------------------------

def test_non_numeric_exact_match_counts_as_met():
    pattern = make_pattern({"status": "active"})
    result = FingerprintEvaluator().evaluate(pattern, {"status": "active"})
    assert result.score == 1.0


def test_non_numeric_mismatch_not_met():
    pattern = make_pattern({"status": "active"})
    result = FingerprintEvaluator().evaluate(pattern, {"status": "inactive"})
    assert result.score == 0.0


def test_non_numeric_missing_metric_not_met():
    """Metric key absent — treated as None, does not equal string threshold."""
    pattern = make_pattern({"status": "active"})
    result = FingerprintEvaluator().evaluate(pattern, {})
    assert result.score == 0.0


def test_mixed_numeric_and_non_numeric_thresholds():
    """One numeric met, one non-numeric met, one non-numeric missed."""
    pattern = make_pattern({"logins": 5, "status": "active", "tier": "gold"})
    metrics = {"logins": 10, "status": "active", "tier": "silver"}
    result = FingerprintEvaluator().evaluate(pattern, metrics)
    assert round(result.score, 4) == round(2 / 3, 4)
    assert result.risk_level == "medium"


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------

def test_result_contains_correct_pattern_name():
    pattern = make_pattern({"logins": 1})
    result = FingerprintEvaluator().evaluate(pattern, {"logins": 5})
    assert result.pattern_name == "test_pattern"


def test_result_details_contains_matched_total_and_metrics():
    pattern = make_pattern({"logins": 5, "sessions": 3})
    metrics = {"logins": 10, "sessions": 1}
    result = FingerprintEvaluator().evaluate(pattern, metrics)
    assert result.details["matched"] == 1
    assert result.details["total"] == 2
    assert result.details["metrics"] == metrics


def test_result_details_matched_equals_zero_when_none_met():
    pattern = make_pattern({"logins": 100})
    result = FingerprintEvaluator().evaluate(pattern, {"logins": 1})
    assert result.details["matched"] == 0
