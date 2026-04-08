"""Unit tests for InsightGenerator — pure generation logic, no DB required."""

from core.insight.generator import InsightGenerator
from core.insight.models import Insight, InsightGenerationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_kpi(kpi_name: str = "avg_logins", confidence: float = 0.8,
             entity_type: str = "student", entity_id: int = 0) -> dict:
    return {
        "kpi_name": kpi_name,
        "source_pattern": "auto",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "formula": "avg(logins)",
        "confidence": confidence,
        "sample_size": 10,
    }


def make_fingerprint(pattern_name: str = "disengagement", risk_level: str = "high",
                     score: float = 0.9, entity_type: str = "student",
                     entity_id: str = "student_1") -> dict:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "pattern_name": pattern_name,
        "score": score,
        "risk_level": risk_level,
    }


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------

def test_no_kpis_no_fingerprints_returns_empty_insights():
    result = InsightGenerator().generate_insights([], [], entity_id="test_entity", entity_type="test_type")
    assert result.insights == []


def test_no_kpis_no_fingerprints_generated_count_is_zero():
    result = InsightGenerator().generate_insights([], [], entity_id="test_entity", entity_type="test_type")
    assert result.generated_count == 0


def test_no_kpis_no_fingerprints_analyzed_counts_are_zero():
    result = InsightGenerator().generate_insights([], [], entity_id="test_entity", entity_type="test_type")
    assert result.analyzed_kpis == 0
    assert result.analyzed_fingerprints == 0


def test_empty_inputs_returns_insight_generation_result():
    result = InsightGenerator().generate_insights([], [], entity_id="test_entity", entity_type="test_type")
    assert isinstance(result, InsightGenerationResult)


# ---------------------------------------------------------------------------
# KPI insights — confidence threshold
# ---------------------------------------------------------------------------

def test_high_confidence_kpi_produces_insight():
    result = InsightGenerator().generate_insights([make_kpi(confidence=0.8)], [], entity_id="test_entity", entity_type="test_type")
    assert len(result.insights) == 1


def test_kpi_confidence_above_threshold_produces_kpi_insight_type():
    result = InsightGenerator().generate_insights([make_kpi(confidence=0.9)], [], entity_id="test_entity", entity_type="test_type")
    assert result.insights[0].insight_type == "kpi"


def test_kpi_confidence_exactly_0_7_does_not_trigger():
    """Threshold is strictly > 0.7 — exactly 0.7 must not produce an insight."""
    result = InsightGenerator().generate_insights([make_kpi(confidence=0.7)], [], entity_id="test_entity", entity_type="test_type")
    assert result.insights == []


def test_kpi_confidence_below_threshold_produces_no_insight():
    result = InsightGenerator().generate_insights([make_kpi(confidence=0.5)], [], entity_id="test_entity", entity_type="test_type")
    assert result.insights == []


def test_kpi_confidence_zero_produces_no_insight():
    result = InsightGenerator().generate_insights([make_kpi(confidence=0.0)], [], entity_id="test_entity", entity_type="test_type")
    assert result.insights == []


# ---------------------------------------------------------------------------
# Fingerprint insights — risk level threshold
# ---------------------------------------------------------------------------

def test_high_risk_fingerprint_produces_insight():
    result = InsightGenerator().generate_insights([], [make_fingerprint(risk_level="high")], entity_id="test_entity", entity_type="test_type")
    assert len(result.insights) == 1


def test_high_risk_fingerprint_produces_risk_insight_type():
    result = InsightGenerator().generate_insights([], [make_fingerprint(risk_level="high")], entity_id="test_entity", entity_type="test_type")
    assert result.insights[0].insight_type == "risk"


def test_medium_risk_fingerprint_produces_no_insight():
    result = InsightGenerator().generate_insights([], [make_fingerprint(risk_level="medium")], entity_id="test_entity", entity_type="test_type")
    assert result.insights == []


def test_low_risk_fingerprint_produces_no_insight():
    result = InsightGenerator().generate_insights([], [make_fingerprint(risk_level="low")], entity_id="test_entity", entity_type="test_type")
    assert result.insights == []


# ---------------------------------------------------------------------------
# Multiple KPIs
# ---------------------------------------------------------------------------

def test_multiple_qualifying_kpis_produce_multiple_insights():
    kpis = [make_kpi("avg_logins", 0.9), make_kpi("avg_sessions", 0.85)]
    result = InsightGenerator().generate_insights(kpis, [], entity_id="test_entity", entity_type="test_type")
    assert len(result.insights) == 2


def test_mixed_kpis_only_qualifying_ones_produce_insights():
    kpis = [make_kpi("avg_logins", 0.9), make_kpi("avg_sessions", 0.5)]
    result = InsightGenerator().generate_insights(kpis, [], entity_id="test_entity", entity_type="test_type")
    assert len(result.insights) == 1
    assert result.insights[0].source_kpis == {"avg_logins": 0.9}


def test_both_qualifying_kpi_and_fingerprint_produce_two_insights():
    kpis = [make_kpi(confidence=0.9)]
    fingerprints = [make_fingerprint(risk_level="high")]
    result = InsightGenerator().generate_insights(kpis, fingerprints, entity_id="test_entity", entity_type="test_type")
    assert result.generated_count == 2


def test_multiple_high_risk_fingerprints_produce_multiple_insights():
    fps = [make_fingerprint(risk_level="high"), make_fingerprint(risk_level="high", entity_id="s2")]
    result = InsightGenerator().generate_insights([], fps, entity_id="test_entity", entity_type="test_type")
    assert len(result.insights) == 2


# ---------------------------------------------------------------------------
# Analyzed counts
# ---------------------------------------------------------------------------

def test_analyzed_kpis_reflects_input_length():
    kpis = [make_kpi(confidence=0.9), make_kpi(confidence=0.5)]
    result = InsightGenerator().generate_insights(kpis, [], entity_id="test_entity", entity_type="test_type")
    assert result.analyzed_kpis == 2


def test_analyzed_fingerprints_reflects_input_length():
    fps = [make_fingerprint(), make_fingerprint(entity_id="s2"), make_fingerprint(entity_id="s3")]
    result = InsightGenerator().generate_insights([], fps, entity_id="test_entity", entity_type="test_type")
    assert result.analyzed_fingerprints == 3


def test_generated_count_matches_insights_list_length():
    kpis = [make_kpi(confidence=0.9)]
    fps = [make_fingerprint(risk_level="high")]
    result = InsightGenerator().generate_insights(kpis, fps, entity_id="test_entity", entity_type="test_type")
    assert result.generated_count == len(result.insights)


# ---------------------------------------------------------------------------
# Output structure matches schema
# ---------------------------------------------------------------------------

def test_kpi_insight_is_insight_instance():
    result = InsightGenerator().generate_insights([make_kpi(confidence=0.8)], [], entity_id="test_entity", entity_type="test_type")
    assert isinstance(result.insights[0], Insight)


def test_kpi_insight_title_contains_kpi_name():
    result = InsightGenerator().generate_insights([make_kpi("avg_logins", confidence=0.8)], [], entity_id="test_entity", entity_type="test_type")
    assert "avg_logins" in result.insights[0].title


def test_kpi_insight_body_contains_kpi_name():
    result = InsightGenerator().generate_insights([make_kpi("avg_logins", confidence=0.8)], [], entity_id="test_entity", entity_type="test_type")
    assert "avg_logins" in result.insights[0].body


def test_kpi_insight_body_contains_confidence():
    result = InsightGenerator().generate_insights([make_kpi("avg_logins", confidence=0.8)], [], entity_id="test_entity", entity_type="test_type")
    assert "0.8" in result.insights[0].body


def test_kpi_insight_confidence_matches_kpi_confidence():
    result = InsightGenerator().generate_insights([make_kpi(confidence=0.85)], [], entity_id="test_entity", entity_type="test_type")
    assert result.insights[0].confidence == 0.85


def test_kpi_insight_source_kpis_contains_kpi_name_and_confidence():
    result = InsightGenerator().generate_insights([make_kpi("avg_logins", confidence=0.8)], [], entity_id="test_entity", entity_type="test_type")
    assert result.insights[0].source_kpis == {"avg_logins": 0.8}


def test_kpi_insight_source_patterns_is_empty():
    result = InsightGenerator().generate_insights([make_kpi(confidence=0.8)], [], entity_id="test_entity", entity_type="test_type")
    assert result.insights[0].source_patterns == {}


def test_risk_insight_title_contains_pattern_name():
    result = InsightGenerator().generate_insights([], [make_fingerprint(pattern_name="disengagement")], entity_id="test_entity", entity_type="test_type")
    assert "disengagement" in result.insights[0].title


def test_risk_insight_body_contains_entity_id():
    result = InsightGenerator().generate_insights([], [make_fingerprint(entity_id="student_42")], entity_id="test_entity", entity_type="test_type")
    assert "student_42" in result.insights[0].body


def test_risk_insight_confidence_matches_fingerprint_score():
    result = InsightGenerator().generate_insights([], [make_fingerprint(score=0.95)], entity_id="test_entity", entity_type="test_type")
    assert result.insights[0].confidence == 0.95


def test_risk_insight_source_patterns_contains_pattern_and_score():
    result = InsightGenerator().generate_insights([], [make_fingerprint(pattern_name="disengagement", score=0.9)], entity_id="test_entity", entity_type="test_type")
    assert result.insights[0].source_patterns == {"disengagement": 0.9}


def test_risk_insight_source_kpis_is_empty():
    result = InsightGenerator().generate_insights([], [make_fingerprint(risk_level="high")], entity_id="test_entity", entity_type="test_type")
    assert result.insights[0].source_kpis == {}


# ---------------------------------------------------------------------------
# Missing fields handled safely
# ---------------------------------------------------------------------------

def test_kpi_missing_kpi_name_uses_unknown_fallback():
    kpi = {"confidence": 0.9, "entity_type": "student"}
    result = InsightGenerator().generate_insights([kpi], [], entity_id="test_entity", entity_type="test_type")
    assert "unknown" in result.insights[0].title


def test_kpi_missing_confidence_defaults_to_zero_no_insight():
    """No confidence key → defaults to 0.0 → below threshold → no insight."""
    kpi = {"kpi_name": "avg_logins", "entity_type": "student"}
    result = InsightGenerator().generate_insights([kpi], [], entity_id="test_entity", entity_type="test_type")
    assert result.insights == []


def test_fingerprint_missing_risk_level_produces_no_insight():
    """No risk_level key → does not equal 'high' → no insight."""
    fp = {"entity_type": "student", "entity_id": "s1", "pattern_name": "x", "score": 0.9}
    result = InsightGenerator().generate_insights([], [fp], entity_id="test_entity", entity_type="test_type")
    assert result.insights == []


def test_fingerprint_missing_pattern_name_uses_unknown_fallback():
    fp = {"entity_type": "student", "entity_id": "s1", "risk_level": "high", "score": 0.9}
    result = InsightGenerator().generate_insights([], [fp], entity_id="test_entity", entity_type="test_type")
    assert "unknown" in result.insights[0].title


def test_fingerprint_missing_entity_id_defaults_to_zero():
    fp = {"entity_type": "student", "pattern_name": "x", "risk_level": "high", "score": 0.9}
    result = InsightGenerator().generate_insights([], [fp], entity_id="test_entity", entity_type="test_type")
    assert result.insights[0].entity_id == 0
