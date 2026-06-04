"""Unit tests for interpret_kpi — deterministic KPI severity rules.

Each KPI is tested for:
  - healthy boundary (suppress=True)
  - warning boundary
  - elevated boundary
  - critical boundary
  - exact threshold boundary values (fence-post checks)
"""

import pytest
from core.insight.generator import interpret_kpi


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_suppressed(result):
    assert result["suppress"] is True, f"Expected suppressed, got {result}"


def assert_not_suppressed(result):
    assert result["suppress"] is False, f"Expected not suppressed, got {result}"


def assert_severity(result, expected):
    assert result["severity"] == expected, (
        f"Expected severity={expected!r}, got {result['severity']!r}"
    )


def assert_has_content(result):
    assert result["title"], "title must be non-empty"
    assert result["body"], "body must be non-empty"
    assert result["recommended_action"], "recommended_action must be non-empty"


# ---------------------------------------------------------------------------
# attendance_percentage
# ---------------------------------------------------------------------------

class TestAttendancePercentage:

    def test_healthy_suppressed(self):
        assert_suppressed(interpret_kpi("attendance_percentage", 0.95, "percent"))

    def test_at_healthy_boundary_suppressed(self):
        # Exactly 0.90 is healthy
        assert_suppressed(interpret_kpi("attendance_percentage", 0.90, "percent"))

    def test_warning_just_below_healthy(self):
        r = interpret_kpi("attendance_percentage", 0.89, "percent")
        assert_not_suppressed(r)
        assert_severity(r, "warning")
        assert_has_content(r)

    def test_warning_midpoint(self):
        r = interpret_kpi("attendance_percentage", 0.80, "percent")
        assert_severity(r, "warning")

    def test_at_warning_lower_boundary(self):
        # Exactly 0.75 is still warning
        r = interpret_kpi("attendance_percentage", 0.75, "percent")
        assert_severity(r, "warning")

    def test_elevated_just_below_warning(self):
        r = interpret_kpi("attendance_percentage", 0.74, "percent")
        assert_severity(r, "elevated")
        assert_has_content(r)

    def test_elevated_midpoint(self):
        r = interpret_kpi("attendance_percentage", 0.60, "percent")
        assert_severity(r, "elevated")

    def test_at_elevated_lower_boundary(self):
        # Exactly 0.50 is still elevated
        r = interpret_kpi("attendance_percentage", 0.50, "percent")
        assert_severity(r, "elevated")

    def test_critical_just_below_elevated(self):
        r = interpret_kpi("attendance_percentage", 0.49, "percent")
        assert_severity(r, "critical")
        assert_has_content(r)

    def test_critical_zero(self):
        r = interpret_kpi("attendance_percentage", 0.0, "percent")
        assert_severity(r, "critical")

    def test_body_contains_percentage(self):
        r = interpret_kpi("attendance_percentage", 0.077, "percent")
        assert "8%" in r["body"] or "7%" in r["body"]  # rounds to nearest %


# ---------------------------------------------------------------------------
# last_activity_days
# ---------------------------------------------------------------------------

class TestLastActivityDays:

    def test_healthy_zero_days(self):
        assert_suppressed(interpret_kpi("last_activity_days", 0, "days"))

    def test_healthy_three_days(self):
        assert_suppressed(interpret_kpi("last_activity_days", 3, "days"))

    def test_warning_four_days(self):
        r = interpret_kpi("last_activity_days", 4, "days")
        assert_severity(r, "warning")
        assert_not_suppressed(r)

    def test_warning_seven_days(self):
        r = interpret_kpi("last_activity_days", 7, "days")
        assert_severity(r, "warning")

    def test_elevated_eight_days(self):
        r = interpret_kpi("last_activity_days", 8, "days")
        assert_severity(r, "elevated")
        assert_has_content(r)

    def test_elevated_thirteen_days(self):
        r = interpret_kpi("last_activity_days", 13, "days")
        assert_severity(r, "elevated")

    def test_critical_fourteen_days(self):
        # 14 aligns with FingerprintGeneratorService stale threshold
        r = interpret_kpi("last_activity_days", 14, "days")
        assert_severity(r, "critical")
        assert_has_content(r)

    def test_critical_large_value(self):
        r = interpret_kpi("last_activity_days", 90, "days")
        assert_severity(r, "critical")

    def test_body_contains_day_count(self):
        r = interpret_kpi("last_activity_days", 18, "days")
        assert "18" in r["body"]

    def test_title_contains_activity_label(self):
        r = interpret_kpi("last_activity_days", 18, "days")
        assert "platform activity" in r["title"]


# ---------------------------------------------------------------------------
# last_login_days
# ---------------------------------------------------------------------------

class TestLastLoginDays:

    def test_healthy_zero(self):
        assert_suppressed(interpret_kpi("last_login_days", 0, "days"))

    def test_healthy_three(self):
        assert_suppressed(interpret_kpi("last_login_days", 3, "days"))

    def test_warning_four(self):
        r = interpret_kpi("last_login_days", 4, "days")
        assert_severity(r, "warning")

    def test_elevated_eight(self):
        r = interpret_kpi("last_login_days", 8, "days")
        assert_severity(r, "elevated")

    def test_critical_fourteen(self):
        r = interpret_kpi("last_login_days", 14, "days")
        assert_severity(r, "critical")

    def test_title_contains_login_label(self):
        r = interpret_kpi("last_login_days", 14, "days")
        assert "login" in r["title"]


# ---------------------------------------------------------------------------
# homeworks_behind
# ---------------------------------------------------------------------------

class TestHomeworksBehind:

    def test_healthy_zero(self):
        assert_suppressed(interpret_kpi("homeworks_behind", 0, "count"))

    def test_warning_one(self):
        r = interpret_kpi("homeworks_behind", 1, "count")
        assert_severity(r, "warning")
        assert_not_suppressed(r)

    def test_warning_two(self):
        r = interpret_kpi("homeworks_behind", 2, "count")
        assert_severity(r, "warning")

    def test_elevated_three(self):
        r = interpret_kpi("homeworks_behind", 3, "count")
        assert_severity(r, "elevated")
        assert_has_content(r)

    def test_elevated_four(self):
        r = interpret_kpi("homeworks_behind", 4, "count")
        assert_severity(r, "elevated")

    def test_critical_five(self):
        r = interpret_kpi("homeworks_behind", 5, "count")
        assert_severity(r, "critical")
        assert_has_content(r)

    def test_critical_ten(self):
        r = interpret_kpi("homeworks_behind", 10, "count")
        assert_severity(r, "critical")

    def test_body_contains_count(self):
        r = interpret_kpi("homeworks_behind", 3, "count")
        assert "3" in r["body"]

    def test_singular_word_for_one(self):
        r = interpret_kpi("homeworks_behind", 1, "count")
        assert "assignment" in r["title"]
        assert "assignments" not in r["title"]


# ---------------------------------------------------------------------------
# avg_hw_score
# ---------------------------------------------------------------------------

class TestAvgHwScore:

    def test_healthy_85(self):
        assert_suppressed(interpret_kpi("avg_hw_score", 85, "score"))

    def test_healthy_100(self):
        assert_suppressed(interpret_kpi("avg_hw_score", 100, "score"))

    def test_warning_84(self):
        r = interpret_kpi("avg_hw_score", 84, "score")
        assert_severity(r, "warning")
        assert_not_suppressed(r)

    def test_warning_70(self):
        r = interpret_kpi("avg_hw_score", 70, "score")
        assert_severity(r, "warning")

    def test_elevated_69(self):
        r = interpret_kpi("avg_hw_score", 69, "score")
        assert_severity(r, "elevated")
        assert_has_content(r)

    def test_elevated_55(self):
        r = interpret_kpi("avg_hw_score", 55, "score")
        assert_severity(r, "elevated")

    def test_critical_54(self):
        r = interpret_kpi("avg_hw_score", 54, "score")
        assert_severity(r, "critical")
        assert_has_content(r)

    def test_critical_zero(self):
        r = interpret_kpi("avg_hw_score", 0, "score")
        assert_severity(r, "critical")

    def test_body_contains_score(self):
        r = interpret_kpi("avg_hw_score", 62, "score")
        assert "62" in r["body"]


# ---------------------------------------------------------------------------
# submission_rate / assignment_submission_rate
# ---------------------------------------------------------------------------

class TestSubmissionRate:

    def test_healthy_90_percent(self):
        assert_suppressed(interpret_kpi("submission_rate", 0.90, "ratio"))

    def test_healthy_full(self):
        assert_suppressed(interpret_kpi("submission_rate", 1.0, "ratio"))

    def test_warning_89_percent(self):
        r = interpret_kpi("submission_rate", 0.89, "ratio")
        assert_severity(r, "warning")

    def test_warning_75_percent(self):
        r = interpret_kpi("submission_rate", 0.75, "ratio")
        assert_severity(r, "warning")

    def test_elevated_74_percent(self):
        r = interpret_kpi("submission_rate", 0.74, "ratio")
        assert_severity(r, "elevated")

    def test_elevated_50_percent(self):
        r = interpret_kpi("submission_rate", 0.50, "ratio")
        assert_severity(r, "elevated")

    def test_critical_49_percent(self):
        r = interpret_kpi("submission_rate", 0.49, "ratio")
        assert_severity(r, "critical")

    def test_critical_zero(self):
        r = interpret_kpi("submission_rate", 0.0, "ratio")
        assert_severity(r, "critical")

    def test_alias_assignment_submission_rate(self):
        # Both signal names must produce identical severity
        r1 = interpret_kpi("submission_rate", 0.60, "ratio")
        r2 = interpret_kpi("assignment_submission_rate", 0.60, "ratio")
        assert r1["severity"] == r2["severity"]
        assert r1["suppress"] == r2["suppress"]

    def test_body_contains_percentage(self):
        r = interpret_kpi("submission_rate", 0.62, "ratio")
        assert "62%" in r["body"]


# ---------------------------------------------------------------------------
# trigger_completion_rate
# ---------------------------------------------------------------------------

class TestTriggerCompletionRate:

    def test_healthy_60_percent(self):
        assert_suppressed(interpret_kpi("trigger_completion_rate", 0.60, "ratio"))

    def test_healthy_full(self):
        assert_suppressed(interpret_kpi("trigger_completion_rate", 1.0, "ratio"))

    def test_warning_59_percent(self):
        r = interpret_kpi("trigger_completion_rate", 0.59, "ratio")
        assert_severity(r, "warning")

    def test_warning_40_percent(self):
        r = interpret_kpi("trigger_completion_rate", 0.40, "ratio")
        assert_severity(r, "warning")

    def test_elevated_39_percent(self):
        r = interpret_kpi("trigger_completion_rate", 0.39, "ratio")
        assert_severity(r, "elevated")

    def test_elevated_25_percent(self):
        r = interpret_kpi("trigger_completion_rate", 0.25, "ratio")
        assert_severity(r, "elevated")

    def test_critical_24_percent(self):
        r = interpret_kpi("trigger_completion_rate", 0.24, "ratio")
        assert_severity(r, "critical")
        assert_has_content(r)

    def test_critical_zero(self):
        r = interpret_kpi("trigger_completion_rate", 0.0, "ratio")
        assert_severity(r, "critical")

    def test_body_contains_outreach_label(self):
        r = interpret_kpi("trigger_completion_rate", 0.20, "ratio")
        assert "outreach" in r["body"].lower()


# ---------------------------------------------------------------------------
# intervention_completion_rate
# ---------------------------------------------------------------------------

class TestInterventionCompletionRate:

    def test_healthy_70_percent(self):
        # Healthy threshold is higher for interventions (0.70)
        assert_suppressed(interpret_kpi("intervention_completion_rate", 0.70, "ratio"))

    def test_warning_just_below_healthy(self):
        r = interpret_kpi("intervention_completion_rate", 0.69, "ratio")
        assert_severity(r, "warning")

    def test_warning_50_percent(self):
        r = interpret_kpi("intervention_completion_rate", 0.50, "ratio")
        assert_severity(r, "warning")

    def test_elevated_49_percent(self):
        r = interpret_kpi("intervention_completion_rate", 0.49, "ratio")
        assert_severity(r, "elevated")

    def test_elevated_25_percent(self):
        r = interpret_kpi("intervention_completion_rate", 0.25, "ratio")
        assert_severity(r, "elevated")

    def test_critical_24_percent(self):
        r = interpret_kpi("intervention_completion_rate", 0.24, "ratio")
        assert_severity(r, "critical")

    def test_healthy_threshold_differs_from_trigger_completion(self):
        # intervention_completion healthy bar (0.70) > trigger_completion (0.60)
        v = 0.65
        r_trigger = interpret_kpi("trigger_completion_rate", v, "ratio")
        r_interv  = interpret_kpi("intervention_completion_rate", v, "ratio")
        assert r_trigger["suppress"] is True   # 0.65 ≥ 0.60 → healthy for triggers
        assert r_interv["suppress"] is False   # 0.65 < 0.70 → warning for interventions

    def test_body_contains_intervention_label(self):
        r = interpret_kpi("intervention_completion_rate", 0.10, "ratio")
        assert "intervention" in r["body"].lower()


# ---------------------------------------------------------------------------
# Fallback — unknown KPI names
# ---------------------------------------------------------------------------

class TestFallbackKpi:

    def test_unknown_kpi_not_suppressed(self):
        r = interpret_kpi("some_unknown_metric", 42, "count")
        assert r["suppress"] is False

    def test_unknown_kpi_title_is_none(self):
        r = interpret_kpi("some_unknown_metric", 42, "count")
        assert r["title"] is None

    def test_unknown_kpi_severity_unknown(self):
        r = interpret_kpi("some_unknown_metric", 42, "count")
        assert r["severity"] == "unknown"

    def test_non_numeric_value_falls_back(self):
        r = interpret_kpi("last_activity_days", "not-a-number", "days")
        assert r["suppress"] is False
        assert r["title"] is None

    def test_none_value_falls_back(self):
        r = interpret_kpi("attendance_percentage", None, "percent")
        assert r["suppress"] is False
        assert r["title"] is None


# ---------------------------------------------------------------------------
# interpret_kpi integration with InsightGenerator
# ---------------------------------------------------------------------------

class TestInsightGeneratorInterpretation:
    """Smoke-test the full generate_insights path with value-aware KPI dicts."""

    from core.insight.generator import InsightGenerator
    from core.insight.models import InsightGenerationResult

    def _gen(self, kpis):
        from core.insight.generator import InsightGenerator
        return InsightGenerator().generate_insights(
            kpis, [], entity_id="test", entity_type="student"
        )

    def test_healthy_attendance_suppressed(self):
        result = self._gen([{
            "kpi_name": "attendance_percentage", "value": 0.95,
            "unit": "percent", "confidence": 0.85,
        }])
        assert result.insights == []

    def test_critical_attendance_produces_insight(self):
        result = self._gen([{
            "kpi_name": "attendance_percentage", "value": 0.30,
            "unit": "percent", "confidence": 0.85,
        }])
        assert len(result.insights) == 1
        assert "30%" in result.insights[0].title or "30%" in result.insights[0].body

    def test_critical_activity_insight_title_contains_day_count(self):
        result = self._gen([{
            "kpi_name": "last_activity_days", "value": 18,
            "unit": "days", "confidence": 0.95,
        }])
        assert "18" in result.insights[0].title

    def test_healthy_kpi_still_counts_in_analyzed_total(self):
        result = self._gen([
            {"kpi_name": "attendance_percentage", "value": 0.95,
             "unit": "percent", "confidence": 0.85},
            {"kpi_name": "last_activity_days", "value": 20,
             "unit": "days", "confidence": 0.95},
        ])
        # One suppressed, one critical
        assert result.analyzed_kpis == 2
        assert result.generated_count == 1

    def test_unknown_kpi_uses_generic_title(self):
        result = self._gen([{
            "kpi_name": "some_future_metric", "value": 99,
            "unit": "count", "confidence": 0.85,
        }])
        assert result.insights[0].insight_type == "kpi"
        assert "Engagement signal" in result.insights[0].title

    def test_recommended_action_is_deterministic_for_mapped_kpi(self):
        result = self._gen([{
            "kpi_name": "homeworks_behind", "value": 6,
            "unit": "count", "confidence": 0.95,
        }])
        action = result.insights[0].recommended_action
        assert "Escalate" in action or "escalate" in action.lower()
