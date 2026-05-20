"""Unit tests for MaterialChangeEvaluationService.

Tests cover all 6 V1 rules plus output contract invariants:
  - Rule 1: Confidence delta > 0.20 triggers generate_new
  - Rule 2: Risk escalation (upward only) triggers generate_new
  - Rule 3: New behavioral fingerprint triggers generate_new
  - Rule 4: Stale interpretation triggers generate_new
  - Rule 5: Cross-dimension deterioration (2+ high/critical) triggers generate_new
  - Rule 6: No material change → reuse_existing (default)

All tests are pure and isolated — no database session, no ORM import required.
Interpretation stubs are built with types.SimpleNamespace to avoid ORM coupling.
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from services.material_change_evaluation_service import MaterialChangeEvaluationService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SVC = MaterialChangeEvaluationService()

_BASE_KWARGS = dict(
    entity_id="student_101",
    entity_type="student",
    dimension="engagement",
)


def _fresh_interp(**kwargs) -> SimpleNamespace:
    """Return a SimpleNamespace that mimics a non-stale, active AIInterpretation."""
    defaults = dict(
        id=1,
        is_active=True,
        stale_after=datetime.utcnow() + timedelta(days=7),
        risk_level="low",
        confidence=0.80,
        source_snapshot_json=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _stale_interp(**kwargs) -> SimpleNamespace:
    """Return an interpretation whose stale_after is in the past."""
    return _fresh_interp(stale_after=datetime.utcnow() - timedelta(seconds=1), **kwargs)


def _snapshot_json(pattern_names: list[str]) -> str:
    """Serialize a minimal source_snapshot_json with the given fingerprint names."""
    return json.dumps({"fingerprints": [{"pattern_name": n} for n in pattern_names]})


def _fp(pattern_name: str, risk_level: str = "low") -> dict:
    return {"pattern_name": pattern_name, "risk_level": risk_level}


def _kpi(name: str, confidence: float) -> dict:
    return {"kpi_name": name, "confidence": confidence}


# ---------------------------------------------------------------------------
# Output contract: key presence and mutual exclusivity
# ---------------------------------------------------------------------------

def _assert_contract(result: dict) -> None:
    required_keys = {
        "reuse_existing", "generate_new", "invalidate_existing",
        "reason", "severity", "confidence_delta", "risk_changed",
        "new_fingerprint_detected",
    }
    assert required_keys == set(result.keys()), f"Unexpected keys: {set(result.keys())}"
    assert isinstance(result["reuse_existing"], bool)
    assert isinstance(result["generate_new"], bool)
    assert isinstance(result["invalidate_existing"], bool)
    assert result["reuse_existing"] != result["generate_new"], (
        "Exactly one of reuse_existing / generate_new must be True"
    )
    assert isinstance(result["reason"], str) and result["reason"]
    assert result["severity"] in {"none", "low", "medium", "high"}
    assert result["confidence_delta"] is None or isinstance(result["confidence_delta"], float)
    assert isinstance(result["risk_changed"], bool)
    assert isinstance(result["new_fingerprint_detected"], bool)


# ===========================================================================
# No prior interpretation (base case)
# ===========================================================================

class TestNoPriorInterpretation:
    def test_returns_generate_new(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("disengaged")],
            latest_interpretation=None,
        )
        assert result["generate_new"] is True
        assert result["reuse_existing"] is False

    def test_invalidate_existing_is_false(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=None,
        )
        assert result["invalidate_existing"] is False

    def test_severity_is_medium(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=None,
        )
        assert result["severity"] == "medium"

    def test_risk_changed_and_fingerprint_are_false(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=None,
        )
        assert result["risk_changed"] is False
        assert result["new_fingerprint_detected"] is False

    def test_output_contract_satisfied(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=None,
        )
        _assert_contract(result)


# ===========================================================================
# Rule 4: Stale interpretation
# ===========================================================================

class TestRule4Stale:
    def test_stale_triggers_generate_new(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=_stale_interp(),
        )
        assert result["generate_new"] is True

    def test_stale_severity_is_medium(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=_stale_interp(),
        )
        assert result["severity"] == "medium"

    def test_active_stale_sets_invalidate_existing(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=_stale_interp(is_active=True),
        )
        assert result["invalidate_existing"] is True

    def test_inactive_stale_does_not_set_invalidate_existing(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=_stale_interp(is_active=False),
        )
        assert result["invalidate_existing"] is False

    def test_stale_after_none_does_not_trigger(self):
        interp = _fresh_interp(stale_after=None)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_stale_reason_mentions_stale_after(self):
        interp = _stale_interp()
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert "stale" in result["reason"].lower()

    def test_output_contract_satisfied(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=_stale_interp(),
        )
        _assert_contract(result)


# ===========================================================================
# Rule 2: Risk escalation
# ===========================================================================

class TestRule2RiskEscalation:
    def test_low_to_high_triggers_generate_new(self):
        interp = _fresh_interp(risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[],
            current_fingerprints=[_fp("disengaged", "high")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True
        assert result["risk_changed"] is True

    def test_severity_is_high_on_escalation(self):
        interp = _fresh_interp(risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[],
            current_fingerprints=[_fp("x", "critical")],
            latest_interpretation=interp,
        )
        assert result["severity"] == "high"

    def test_deescalation_does_not_trigger(self):
        interp = _fresh_interp(risk_level="high")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("x", "low")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_same_risk_does_not_trigger(self):
        interp = _fresh_interp(risk_level="medium")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("x", "medium")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_unknown_prior_to_low_current_triggers_escalation(self):
        # "unknown" has rank -1; "low" has rank 0 — any known risk is above unknown
        interp = _fresh_interp(risk_level="unknown")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("x", "low")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True
        assert result["risk_changed"] is True

    def test_medium_to_critical_triggers(self):
        interp = _fresh_interp(risk_level="medium")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[],
            current_fingerprints=[_fp("x", "critical")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True
        assert result["risk_changed"] is True

    def test_output_contract_satisfied(self):
        interp = _fresh_interp(risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[],
            current_fingerprints=[_fp("x", "high")],
            latest_interpretation=interp,
        )
        _assert_contract(result)


# ===========================================================================
# Rule 3: New fingerprint
# ===========================================================================

class TestRule3NewFingerprint:
    def test_new_pattern_triggers_generate_new(self):
        interp = _fresh_interp(
            source_snapshot_json=_snapshot_json(["pattern_A"]),
        )
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("pattern_A"), _fp("pattern_B")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True
        assert result["new_fingerprint_detected"] is True

    def test_new_fingerprint_severity_is_medium(self):
        interp = _fresh_interp(source_snapshot_json=_snapshot_json(["pattern_A"]))
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("pattern_A"), _fp("pattern_B")],
            latest_interpretation=interp,
        )
        assert result["severity"] == "medium"

    def test_same_fingerprints_do_not_trigger(self):
        interp = _fresh_interp(source_snapshot_json=_snapshot_json(["pattern_A"]))
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("pattern_A")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_empty_prior_snapshot_does_not_trigger(self):
        interp = _fresh_interp(source_snapshot_json=None)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("pattern_X")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_malformed_snapshot_json_does_not_trigger(self):
        interp = _fresh_interp(source_snapshot_json="not-valid-json{{{")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("pattern_X")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_subset_of_prior_fingerprints_does_not_trigger(self):
        interp = _fresh_interp(source_snapshot_json=_snapshot_json(["A", "B", "C"]))
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("A"), _fp("B")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_output_contract_satisfied(self):
        interp = _fresh_interp(source_snapshot_json=_snapshot_json(["A"]))
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("A"), _fp("B_new")],
            latest_interpretation=interp,
        )
        _assert_contract(result)


# ===========================================================================
# Rule 5: Cross-dimension deterioration
# ===========================================================================

class TestRule5CrossDimensionDeterioration:
    def test_two_high_fingerprints_trigger_generate_new(self):
        interp = _fresh_interp()
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("A", "high"), _fp("B", "high")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True

    def test_one_high_one_critical_triggers(self):
        interp = _fresh_interp()
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("A", "high"), _fp("B", "critical")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True

    def test_two_critical_triggers(self):
        interp = _fresh_interp()
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("A", "critical"), _fp("B", "critical")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True

    def test_one_high_fingerprint_does_not_trigger(self):
        # Prior risk="high" prevents Rule 2 from firing on the single high fingerprint.
        # Rule 5 needs 2+ at high/critical; one high + one medium is not enough.
        interp = _fresh_interp(risk_level="high")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("A", "high"), _fp("B", "medium")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_two_medium_fingerprints_do_not_trigger(self):
        # Prior risk="medium" prevents Rule 2 from firing. Medium fingerprints are
        # below the _DETERIORATION_RISK_FLOOR (high), so Rule 5 count stays at 0.
        interp = _fresh_interp(risk_level="medium")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("A", "medium"), _fp("B", "medium")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_severity_is_high_on_cross_dimension(self):
        interp = _fresh_interp()
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("A", "high"), _fp("B", "high")],
            latest_interpretation=interp,
        )
        assert result["severity"] == "high"

    def test_output_contract_satisfied(self):
        interp = _fresh_interp()
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.8)],
            current_fingerprints=[_fp("A", "high"), _fp("B", "critical")],
            latest_interpretation=interp,
        )
        _assert_contract(result)


# ===========================================================================
# Rule 1: Confidence delta
# ===========================================================================

class TestRule1ConfidenceDelta:
    def test_delta_above_threshold_triggers_generate_new(self):
        interp = _fresh_interp(confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.50)],  # delta = |0.50 - 0.80| = 0.30
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True

    def test_delta_below_threshold_does_not_trigger(self):
        # delta = |0.62 - 0.80| = 0.18, clearly below 0.20 threshold
        interp = _fresh_interp(confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.62)],
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is False

    def test_delta_just_above_threshold_triggers(self):
        interp = _fresh_interp(confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.59)],  # delta = 0.21
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True

    def test_confidence_delta_value_is_reported(self):
        interp = _fresh_interp(confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.50)],
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert result["confidence_delta"] is not None
        assert abs(result["confidence_delta"] - 0.30) < 1e-9

    def test_severity_is_low_on_confidence_delta(self):
        interp = _fresh_interp(confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.50)],
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert result["severity"] == "low"

    def test_no_prior_confidence_returns_none_delta(self):
        interp = _fresh_interp(confidence=None)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.50)],
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert result["confidence_delta"] is None
        assert result["generate_new"] is False

    def test_no_current_kpis_returns_none_delta(self):
        interp = _fresh_interp(confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[],
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert result["confidence_delta"] is None
        assert result["generate_new"] is False

    def test_multi_kpi_aggregate_is_mean(self):
        # mean([0.40, 0.60]) = 0.50; prior = 0.80; delta = 0.30 > 0.20
        interp = _fresh_interp(confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("A", 0.40), _kpi("B", 0.60)],
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True

    def test_output_contract_satisfied(self):
        interp = _fresh_interp(confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.50)],
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        _assert_contract(result)


# ===========================================================================
# Rule 6: No material change — reuse
# ===========================================================================

class TestRule6Reuse:
    def test_no_change_returns_reuse_existing(self):
        interp = _fresh_interp(confidence=0.80, risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.80)],
            current_fingerprints=[_fp("A", "low")],
            latest_interpretation=interp,
        )
        assert result["reuse_existing"] is True
        assert result["generate_new"] is False

    def test_reuse_severity_is_none(self):
        interp = _fresh_interp(confidence=0.80, risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.80)],
            current_fingerprints=[_fp("A", "low")],
            latest_interpretation=interp,
        )
        assert result["severity"] == "none"

    def test_reuse_invalidate_existing_is_false(self):
        interp = _fresh_interp(confidence=0.80, risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.80)],
            current_fingerprints=[_fp("A", "low")],
            latest_interpretation=interp,
        )
        assert result["invalidate_existing"] is False

    def test_reuse_risk_changed_and_fingerprint_are_false(self):
        interp = _fresh_interp(confidence=0.80, risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.80)],
            current_fingerprints=[_fp("A", "low")],
            latest_interpretation=interp,
        )
        assert result["risk_changed"] is False
        assert result["new_fingerprint_detected"] is False

    def test_output_contract_satisfied(self):
        interp = _fresh_interp(confidence=0.80, risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.80)],
            current_fingerprints=[_fp("A", "low")],
            latest_interpretation=interp,
        )
        _assert_contract(result)

    def test_reason_mentions_entity_id(self):
        interp = _fresh_interp(confidence=0.80, risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.80)],
            current_fingerprints=[_fp("A", "low")],
            latest_interpretation=interp,
        )
        assert "student_101" in result["reason"]


# ===========================================================================
# Rule priority: stale preempts other rules
# ===========================================================================

class TestRulePriority:
    def test_stale_preempts_risk_escalation(self):
        interp = _stale_interp(risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[],
            current_fingerprints=[_fp("x", "critical")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True
        assert result["risk_changed"] is False  # stale fired first
        assert "stale" in result["reason"].lower()

    def test_stale_preempts_confidence_delta(self):
        interp = _stale_interp(confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.40)],  # delta 0.40 would trigger rule 1
            current_fingerprints=[],
            latest_interpretation=interp,
        )
        assert "stale" in result["reason"].lower()

    def test_risk_escalation_preempts_confidence_delta(self):
        interp = _fresh_interp(risk_level="low", confidence=0.80)
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[_kpi("logins", 0.40)],  # delta 0.40, but risk escalation fires first
            current_fingerprints=[_fp("x", "high")],
            latest_interpretation=interp,
        )
        assert result["risk_changed"] is True
        assert result["severity"] == "high"


# ===========================================================================
# invalidate_existing logic
# ===========================================================================

class TestInvalidateExisting:
    def test_active_prior_generates_with_invalidate_true(self):
        interp = _fresh_interp(is_active=True, risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[],
            current_fingerprints=[_fp("x", "high")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True
        assert result["invalidate_existing"] is True

    def test_inactive_prior_generates_with_invalidate_false(self):
        interp = _fresh_interp(is_active=False, risk_level="low")
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[],
            current_fingerprints=[_fp("x", "high")],
            latest_interpretation=interp,
        )
        assert result["generate_new"] is True
        assert result["invalidate_existing"] is False

    def test_none_prior_never_sets_invalidate_existing(self):
        result = SVC.evaluate_material_change(
            **_BASE_KWARGS,
            current_kpis=[], current_fingerprints=[],
            latest_interpretation=None,
        )
        assert result["invalidate_existing"] is False


# ===========================================================================
# _infer_current_risk helper
# ===========================================================================

class TestInferCurrentRisk:
    def test_empty_fingerprints_returns_unknown(self):
        assert SVC._infer_current_risk([]) == "unknown"

    def test_single_fingerprint_returns_its_risk(self):
        assert SVC._infer_current_risk([_fp("A", "medium")]) == "medium"

    def test_returns_max_risk(self):
        fps = [_fp("A", "low"), _fp("B", "critical"), _fp("C", "medium")]
        assert SVC._infer_current_risk(fps) == "critical"

    def test_unknown_risk_level_is_lowest(self):
        fps = [_fp("A", "unknown"), _fp("B", "low")]
        assert SVC._infer_current_risk(fps) == "low"


# ===========================================================================
# _aggregate_confidence helper
# ===========================================================================

class TestAggregateConfidence:
    def test_empty_kpis_returns_none(self):
        assert SVC._aggregate_confidence([]) is None

    def test_single_kpi_returns_its_confidence(self):
        assert SVC._aggregate_confidence([_kpi("A", 0.75)]) == pytest.approx(0.75)

    def test_multiple_kpis_returns_mean(self):
        kpis = [_kpi("A", 0.60), _kpi("B", 0.80)]
        assert SVC._aggregate_confidence(kpis) == pytest.approx(0.70)


# ===========================================================================
# _compute_confidence_delta helper
# ===========================================================================

class TestComputeConfidenceDelta:
    def test_none_prior_returns_none(self):
        assert SVC._compute_confidence_delta([_kpi("A", 0.5)], None) is None

    def test_empty_kpis_returns_none(self):
        assert SVC._compute_confidence_delta([], 0.80) is None

    def test_returns_absolute_delta(self):
        delta = SVC._compute_confidence_delta([_kpi("A", 0.50)], 0.80)
        assert delta == pytest.approx(0.30)

    def test_delta_is_absolute_when_current_higher(self):
        delta = SVC._compute_confidence_delta([_kpi("A", 0.90)], 0.60)
        assert delta == pytest.approx(0.30)
