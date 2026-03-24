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


# ---------------------------------------------------------------------------
# Real DB TriggerType values — _actions_for
# ---------------------------------------------------------------------------

def test_actions_for_inclass_low_returns_outbound():
    actions = TriggerEvaluator()._actions_for("InClass", "Low")
    assert actions == ["queue_outbound_message"]


def test_actions_for_inclass_high_returns_outbound():
    actions = TriggerEvaluator()._actions_for("InClass", "High")
    assert actions == ["queue_outbound_message"]


def test_actions_for_inclass_unknown_returns_outbound():
    actions = TriggerEvaluator()._actions_for("InClass", "Unknown")
    assert actions == ["queue_outbound_message"]


def test_actions_for_postinterview_low_returns_outbound():
    actions = TriggerEvaluator()._actions_for("PostInterview", "Low")
    assert actions == ["queue_outbound_message"]


def test_actions_for_all_real_trigger_types_produce_outbound_action():
    real_types = ["All", "Capstone", "InClass", "InterviewPast4Wks",
                  "InterviewPrep", "IPBC", "PostInterview"]
    for trigger_type in real_types:
        for level in ("Low", "High", "Unknown"):
            actions = TriggerEvaluator()._actions_for(trigger_type, level)
            assert actions == ["queue_outbound_message"], (
                f"Expected ['queue_outbound_message'] for ({trigger_type!r}, {level!r}), got {actions}"
            )


# ---------------------------------------------------------------------------
# KPI column lookup — TriggerData columns read via getattr
# ---------------------------------------------------------------------------

class FakeRuleKPI:
    """Mirrors CB_ID=1 from AI_ChatBot_TriggerRules."""
    CB_ID       = 1
    TriggerType = "InClass"
    KPI         = "Past10DaysLogon"
    TriggerLow  = 4.0
    TriggerHigh = 8.0


def test_kpi_column_past10dayslogon_low_is_read_correctly():
    """KPI value < TriggerLow must produce level=Low, not Unknown."""
    class StudentLow:
        Past10DaysLogon = 2   # below TriggerLow=4

    result = TriggerEvaluator().evaluate(FakeRuleKPI(), StudentLow(), event_id="K1")

    assert result["trigger_level"] == "Low", \
        f"Expected Low, got {result['trigger_level']!r} — KPI column not read"
    assert result["actions_planned"] == ["queue_outbound_message"]


def test_kpi_column_past10dayslogon_high_is_read_correctly():
    """KPI value > TriggerHigh must produce level=High, not Unknown."""
    class StudentHigh:
        Past10DaysLogon = 9   # above TriggerHigh=8

    result = TriggerEvaluator().evaluate(FakeRuleKPI(), StudentHigh(), event_id="K2")

    assert result["trigger_level"] == "High", \
        f"Expected High, got {result['trigger_level']!r} — KPI column not read"
    assert result["actions_planned"] == ["queue_outbound_message"]


def test_kpi_column_missing_from_student_falls_back_to_unknown():
    """If student object lacks the KPI attribute, level must be Unknown — not an error."""
    class StudentNoKPI:
        pass  # Past10DaysLogon not defined

    result = TriggerEvaluator().evaluate(FakeRuleKPI(), StudentNoKPI(), event_id="K3")

    assert result["trigger_level"] == "Unknown"


# ---------------------------------------------------------------------------
# message_text — prompt selection from rule columns
# ---------------------------------------------------------------------------

class FakeRuleWithPrompts:
    """Rule with both prompt columns populated."""
    CB_ID                    = 1
    TriggerType              = "InClass"
    KPI                      = "Past10DaysLogon"
    TriggerLow               = 4.0
    TriggerHigh              = 8.0
    ChatGPTPromptLowTrigger  = "You are falling behind. Please log in and catch up."
    ChatGPTPromptHighTrigger = "Great work! You are ahead of the curve."


class FakeRuleNoPrompts:
    """Rule with both prompt columns absent (duck-typed fake, no attributes)."""
    CB_ID       = 1
    TriggerType = "InClass"
    KPI         = "Past10DaysLogon"
    TriggerLow  = 4.0
    TriggerHigh = 8.0
    # ChatGPTPromptLowTrigger and ChatGPTPromptHighTrigger intentionally omitted


class FakeRuleNullPrompts:
    """Rule with prompt columns present but set to None."""
    CB_ID                    = 1
    TriggerType              = "InClass"
    KPI                      = "Past10DaysLogon"
    TriggerLow               = 4.0
    TriggerHigh              = 8.0
    ChatGPTPromptLowTrigger  = None
    ChatGPTPromptHighTrigger = None


def test_message_text_key_is_present_in_result():
    """evaluate() must always return a message_text key."""
    class StudentLow:
        Past10DaysLogon = 2

    result = TriggerEvaluator().evaluate(FakeRuleWithPrompts(), StudentLow(), event_id="M1")

    assert "message_text" in result


def test_low_trigger_uses_chatgpt_prompt_low_trigger():
    """When trigger_level is Low, message_text must equal ChatGPTPromptLowTrigger."""
    class StudentLow:
        Past10DaysLogon = 2  # below TriggerLow=4

    result = TriggerEvaluator().evaluate(FakeRuleWithPrompts(), StudentLow(), event_id="M2")

    assert result["trigger_level"] == "Low"
    assert result["message_text"] == "You are falling behind. Please log in and catch up."


def test_high_trigger_uses_chatgpt_prompt_high_trigger():
    """When trigger_level is High, message_text must equal ChatGPTPromptHighTrigger."""
    class StudentHigh:
        Past10DaysLogon = 9  # above TriggerHigh=8

    result = TriggerEvaluator().evaluate(FakeRuleWithPrompts(), StudentHigh(), event_id="M3")

    assert result["trigger_level"] == "High"
    assert result["message_text"] == "Great work! You are ahead of the curve."


def test_missing_prompt_attribute_falls_back_to_hardcoded_string():
    """When prompt columns are absent from the rule, fallback to hardcoded string."""
    class StudentLow:
        Past10DaysLogon = 2  # below TriggerLow=4

    result = TriggerEvaluator().evaluate(FakeRuleNoPrompts(), StudentLow(), event_id="M4")

    assert result["trigger_level"] == "Low"
    assert result["message_text"] == "Trigger InClass level Low"


def test_null_prompt_falls_back_to_hardcoded_string():
    """When prompt columns are None, fallback to hardcoded string."""
    class StudentLow:
        Past10DaysLogon = 2  # below TriggerLow=4

    result = TriggerEvaluator().evaluate(FakeRuleNullPrompts(), StudentLow(), event_id="M5")

    assert result["trigger_level"] == "Low"
    assert result["message_text"] == "Trigger InClass level Low"


def test_unknown_trigger_level_uses_fallback_string():
    """When trigger_level is Unknown, message_text is always the hardcoded fallback."""
    class StudentNoKPI:
        pass  # Past10DaysLogon not defined — produces Unknown

    result = TriggerEvaluator().evaluate(FakeRuleWithPrompts(), StudentNoKPI(), event_id="M6")

    assert result["trigger_level"] == "Unknown"
    assert result["message_text"] == "Trigger InClass level Unknown"


def test_none_trigger_level_uses_fallback_string():
    """When trigger_level is None (within range), message_text is the hardcoded fallback."""
    class StudentInRange:
        Past10DaysLogon = 6  # within [4, 8]

    result = TriggerEvaluator().evaluate(FakeRuleWithPrompts(), StudentInRange(), event_id="M7")

    assert result["trigger_level"] == "None"
    assert result["message_text"] == "Trigger InClass level None"


def test_existing_result_keys_unchanged_after_message_text_added():
    """Adding message_text must not remove or rename any existing result keys."""
    class StudentLow:
        Past10DaysLogon = 2

    result = TriggerEvaluator().evaluate(FakeRuleWithPrompts(), StudentLow(), event_id="M8")

    assert "event_id"        in result
    assert "trigger_level"   in result
    assert "actions_planned" in result
    assert "notes"           in result
    assert "message_text"    in result
