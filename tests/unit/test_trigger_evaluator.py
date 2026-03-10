"""Unit tests for TriggerEvaluator — pure evaluation logic, no DB required."""

from services.trigger_processing_service import TriggerEvaluator


# ---------------------------------------------------------------------------
# Fakes — duck-typed stand-ins for TriggerRule and TriggerData ORM objects
# ---------------------------------------------------------------------------

class FakeRule:
    CB_ID = 1
    TriggerType = "nudge_needed"
    KPI = "PerComp_Act"
    TriggerLow = 0.5
    TriggerHigh = 0.9


class FakeStudent:
    """Student with PerComp_Act set; override per test as needed."""
    PerComp_Act = 0.7  # within range by default


# ---------------------------------------------------------------------------
# _get_kpi_value
# ---------------------------------------------------------------------------

def test_get_kpi_value_returns_float_when_attribute_exists():
    student = FakeStudent()
    result = TriggerEvaluator()._get_kpi_value(student, "PerComp_Act")
    assert result == 0.7


def test_get_kpi_value_returns_none_when_student_is_none():
    result = TriggerEvaluator()._get_kpi_value(None, "PerComp_Act")
    assert result is None


def test_get_kpi_value_returns_none_when_kpi_is_none():
    result = TriggerEvaluator()._get_kpi_value(FakeStudent(), None)
    assert result is None


def test_get_kpi_value_returns_none_when_attribute_missing():
    result = TriggerEvaluator()._get_kpi_value(FakeStudent(), "NonExistentKPI")
    assert result is None


# ---------------------------------------------------------------------------
# _compute_level
# ---------------------------------------------------------------------------

def test_compute_level_returns_low_when_value_below_trigger_low():
    level = TriggerEvaluator()._compute_level(0.3, FakeRule())
    assert level == "Low"


def test_compute_level_returns_high_when_value_above_trigger_high():
    level = TriggerEvaluator()._compute_level(0.95, FakeRule())
    assert level == "High"


def test_compute_level_returns_none_when_value_within_range():
    level = TriggerEvaluator()._compute_level(0.7, FakeRule())
    assert level == "None"


def test_compute_level_returns_unknown_when_value_is_none():
    level = TriggerEvaluator()._compute_level(None, FakeRule())
    assert level == "Unknown"


def test_compute_level_returns_unknown_when_both_thresholds_absent():
    class NoThresholds:
        TriggerLow = None
        TriggerHigh = None

    level = TriggerEvaluator()._compute_level(0.5, NoThresholds())
    assert level == "Unknown"


def test_compute_level_at_exact_low_boundary_is_not_low():
    """Strictly less-than — value equal to TriggerLow is not "Low"."""
    level = TriggerEvaluator()._compute_level(0.5, FakeRule())
    assert level == "None"


def test_compute_level_at_exact_high_boundary_is_not_high():
    """Strictly greater-than — value equal to TriggerHigh is not "High"."""
    level = TriggerEvaluator()._compute_level(0.9, FakeRule())
    assert level == "None"


# ---------------------------------------------------------------------------
# _actions_for
# ---------------------------------------------------------------------------

def test_actions_for_nudge_needed_low_returns_nudge():
    actions = TriggerEvaluator()._actions_for("nudge_needed", "Low")
    assert actions == ["queue_nudge_message"]


def test_actions_for_nudge_needed_high_returns_nudge():
    actions = TriggerEvaluator()._actions_for("nudge_needed", "High")
    assert actions == ["queue_nudge_message"]


def test_actions_for_progress_milestone_returns_congrats():
    actions = TriggerEvaluator()._actions_for("progress_milestone", "Low")
    assert actions == ["queue_congrats_message"]


def test_actions_for_unknown_combination_returns_empty_list():
    actions = TriggerEvaluator()._actions_for("alien_signal", "Low")
    assert actions == []


def test_actions_for_none_trigger_type_returns_empty_list():
    actions = TriggerEvaluator()._actions_for(None, "Low")
    assert actions == []


# ---------------------------------------------------------------------------
# evaluate — full integration of all three helpers
# ---------------------------------------------------------------------------

def test_evaluate_below_low_returns_correct_shape_and_level():
    class LowStudent:
        PerComp_Act = 0.3  # below TriggerLow 0.5

    result = TriggerEvaluator().evaluate(FakeRule(), LowStudent(), event_id="E1")

    assert result["event_id"] == "E1"
    assert result["trigger_level"] == "Low"
    assert result["actions_planned"] == ["queue_nudge_message"]
    assert isinstance(result["notes"], str) and len(result["notes"]) > 0


def test_evaluate_above_high_returns_high_level():
    class HighStudent:
        PerComp_Act = 0.95  # above TriggerHigh 0.9

    result = TriggerEvaluator().evaluate(FakeRule(), HighStudent(), event_id="E2")

    assert result["trigger_level"] == "High"
    assert result["actions_planned"] == ["queue_nudge_message"]


def test_evaluate_within_range_returns_none_level():
    class InRangeStudent:
        PerComp_Act = 0.7  # within [0.5, 0.9]

    result = TriggerEvaluator().evaluate(FakeRule(), InRangeStudent(), event_id="E3")

    assert result["trigger_level"] == "None"
    assert result["actions_planned"] == []


def test_evaluate_missing_kpi_returns_unknown_level():
    class NoKpiStudent:
        pass  # PerComp_Act not defined

    result = TriggerEvaluator().evaluate(FakeRule(), NoKpiStudent(), event_id="E4")

    assert result["trigger_level"] == "Unknown"
    assert result["actions_planned"] == ["queue_nudge_message"]


def test_evaluate_none_student_returns_unknown_level():
    result = TriggerEvaluator().evaluate(FakeRule(), None, event_id="E5")

    assert result["trigger_level"] == "Unknown"


def test_evaluate_result_always_contains_required_keys():
    result = TriggerEvaluator().evaluate(FakeRule(), FakeStudent(), event_id="E6")

    assert "event_id"        in result
    assert "trigger_level"   in result
    assert "actions_planned" in result
    assert "notes"           in result


def test_evaluate_notes_includes_cb_id_kpi_and_level():
    class LowStudent:
        PerComp_Act = 0.3

    result = TriggerEvaluator().evaluate(FakeRule(), LowStudent(), event_id="E7")

    assert "CB_ID=1"        in result["notes"]
    assert "PerComp_Act"    in result["notes"]
    assert "Low"            in result["notes"]
