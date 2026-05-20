"""Unit tests for AIInterpretation ORM model and Pydantic schemas.

Tests cover:
  - Enum completeness and value correctness for all three enum classes
  - ORM model instantiation with required fields
  - Column-level defaults (is_active, interpretation_version, stale_after)
  - Nullable column constraints
  - Pydantic schema: valid data, enum coercion, confidence bounds
  - Pydantic schema: JSON string deserialization via field validators
  - Pydantic schema: ORM → schema round-trip via model_validate
  - AIInterpretationInvalidate: valid and empty-string rejection

All tests are isolated — no database session required.
Column defaults are tested by inspecting SQLAlchemy column metadata and
calling the _stale_after_default function directly.
"""

import json
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from api.schemas.ai_interpretation import (
    AIInterpretationCreate,
    AIInterpretationInvalidate,
    AIInterpretationRead,
)
from services.models import (
    AIInterpretation,
    InterpretationDimension,
    InterpretationGeneratedBy,
    InterpretationRiskLevel,
    _stale_after_default,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

_VALID_CREATE = dict(
    entity_id="student_101",
    entity_type="student",
    dimension="engagement",
    confidence=0.86,
    risk_level="high",
    summary="Student shows strong disengagement signals.",
    recommended_action="Schedule a 1:1 check-in within 48 hours.",
    explainability_json=[
        "Login frequency KPI has 92% confidence disengagement pattern.",
        "Session duration drop indicates active avoidance (81% confidence).",
    ],
    source_metrics_hash="a" * 64,
    generated_by="claude",
    model_name="claude-sonnet-4-6",
)


# ---------------------------------------------------------------------------
# InterpretationDimension enum
# ---------------------------------------------------------------------------

def test_dimension_enum_has_all_expected_values():
    expected = {
        "engagement",
        "assignment_performance",
        "learning_effectiveness",
        "retention_risk",
        "communication_responsiveness",
        "intervention_effectiveness",
    }
    assert {d.value for d in InterpretationDimension} == expected


def test_dimension_enum_has_correct_count():
    assert len(InterpretationDimension) == 6


def test_dimension_enum_is_string_subtype():
    assert isinstance(InterpretationDimension.engagement, str)
    assert InterpretationDimension.retention_risk == "retention_risk"


# ---------------------------------------------------------------------------
# InterpretationRiskLevel enum
# ---------------------------------------------------------------------------

def test_risk_level_enum_has_all_expected_values():
    expected = {"low", "medium", "high", "critical", "unknown"}
    assert {r.value for r in InterpretationRiskLevel} == expected


def test_risk_level_unknown_is_distinct_from_inference_values():
    inference_values = {InterpretationRiskLevel.low, InterpretationRiskLevel.medium,
                        InterpretationRiskLevel.high, InterpretationRiskLevel.critical}
    assert InterpretationRiskLevel.unknown not in inference_values


def test_risk_level_enum_is_string_subtype():
    assert isinstance(InterpretationRiskLevel.high, str)
    assert InterpretationRiskLevel.critical == "critical"


# ---------------------------------------------------------------------------
# InterpretationGeneratedBy enum
# ---------------------------------------------------------------------------

def test_generated_by_enum_has_all_expected_values():
    expected = {"claude", "deterministic_engine", "fallback"}
    assert {g.value for g in InterpretationGeneratedBy} == expected


def test_generated_by_enum_is_string_subtype():
    assert isinstance(InterpretationGeneratedBy.claude, str)
    assert InterpretationGeneratedBy.deterministic_engine == "deterministic_engine"


# ---------------------------------------------------------------------------
# _stale_after_default function
# ---------------------------------------------------------------------------

def test_stale_after_default_returns_approximately_14_days_from_now():
    before = datetime.utcnow() + timedelta(days=14) - timedelta(seconds=1)
    result = _stale_after_default()
    after  = datetime.utcnow() + timedelta(days=14) + timedelta(seconds=1)
    assert before <= result <= after


def test_stale_after_default_returns_datetime():
    assert isinstance(_stale_after_default(), datetime)


# ---------------------------------------------------------------------------
# ORM model — column defaults via SQLAlchemy metadata
# ---------------------------------------------------------------------------

def test_is_active_column_default_is_true():
    col = AIInterpretation.__table__.c.is_active
    assert col.default.arg is True


def test_interpretation_version_column_default_is_1():
    col = AIInterpretation.__table__.c.interpretation_version
    assert col.default.arg == 1


def test_stale_after_column_default_is_callable():
    col = AIInterpretation.__table__.c.stale_after
    assert callable(col.default.arg)


def test_invalidated_at_column_is_nullable():
    col = AIInterpretation.__table__.c.invalidated_at
    assert col.nullable is True


def test_invalidation_reason_column_is_nullable():
    col = AIInterpretation.__table__.c.invalidation_reason
    assert col.nullable is True


def test_recommended_action_column_is_nullable():
    col = AIInterpretation.__table__.c.recommended_action
    assert col.nullable is True


def test_source_metrics_hash_column_length_is_64():
    col = AIInterpretation.__table__.c.source_metrics_hash
    assert col.type.length == 64


# ---------------------------------------------------------------------------
# ORM model — instantiation with required fields
# ---------------------------------------------------------------------------

def test_model_instantiation_sets_required_fields():
    interp = AIInterpretation(
        entity_id="student_101",
        entity_type="student",
        dimension=InterpretationDimension.engagement,
        confidence=0.86,
        risk_level=InterpretationRiskLevel.high,
        summary="Student shows disengagement.",
        generated_by=InterpretationGeneratedBy.claude,
    )
    assert interp.entity_id == "student_101"
    assert interp.entity_type == "student"
    assert interp.confidence == 0.86
    assert interp.summary == "Student shows disengagement."


def test_model_accepts_all_dimension_values():
    for dim in InterpretationDimension:
        interp = AIInterpretation(
            entity_id="s1", entity_type="student",
            dimension=dim, confidence=0.5,
            risk_level=InterpretationRiskLevel.low,
            summary="Test", generated_by=InterpretationGeneratedBy.fallback,
        )
        assert interp.dimension == dim


def test_model_accepts_all_risk_level_values():
    for rl in InterpretationRiskLevel:
        interp = AIInterpretation(
            entity_id="s1", entity_type="student",
            dimension=InterpretationDimension.engagement, confidence=0.5,
            risk_level=rl, summary="Test",
            generated_by=InterpretationGeneratedBy.fallback,
        )
        assert interp.risk_level == rl


# ---------------------------------------------------------------------------
# Pydantic schema — AIInterpretationCreate: valid data
# ---------------------------------------------------------------------------

def test_create_schema_accepts_valid_data():
    schema = AIInterpretationCreate(**_VALID_CREATE)
    assert schema.entity_id == "student_101"
    assert schema.confidence == 0.86
    assert schema.dimension == InterpretationDimension.engagement
    assert schema.risk_level == InterpretationRiskLevel.high
    assert schema.generated_by == InterpretationGeneratedBy.claude


def test_create_schema_interpretation_version_defaults_to_1():
    schema = AIInterpretationCreate(**_VALID_CREATE)
    assert schema.interpretation_version == 1


def test_create_schema_optional_fields_default_none():
    minimal = dict(
        entity_id="s1", entity_type="student",
        dimension="engagement", confidence=0.5,
        risk_level="low", summary="OK",
        generated_by="fallback",
    )
    schema = AIInterpretationCreate(**minimal)
    assert schema.recommended_action is None
    assert schema.explainability_json is None
    assert schema.source_metrics_hash is None
    assert schema.source_snapshot_json is None
    assert schema.model_name is None


# ---------------------------------------------------------------------------
# Pydantic schema — AIInterpretationCreate: enum coercion from string
# ---------------------------------------------------------------------------

def test_create_schema_coerces_dimension_string_to_enum():
    schema = AIInterpretationCreate(**_VALID_CREATE)
    assert isinstance(schema.dimension, InterpretationDimension)


def test_create_schema_coerces_risk_level_string_to_enum():
    schema = AIInterpretationCreate(**_VALID_CREATE)
    assert isinstance(schema.risk_level, InterpretationRiskLevel)


def test_create_schema_coerces_generated_by_string_to_enum():
    schema = AIInterpretationCreate(**_VALID_CREATE)
    assert isinstance(schema.generated_by, InterpretationGeneratedBy)


# ---------------------------------------------------------------------------
# Pydantic schema — AIInterpretationCreate: enum rejection
# ---------------------------------------------------------------------------

def test_create_schema_rejects_invalid_dimension():
    with pytest.raises(ValidationError):
        AIInterpretationCreate(**{**_VALID_CREATE, "dimension": "not_a_dimension"})


def test_create_schema_rejects_invalid_risk_level():
    with pytest.raises(ValidationError):
        AIInterpretationCreate(**{**_VALID_CREATE, "risk_level": "extreme"})


def test_create_schema_rejects_invalid_generated_by():
    with pytest.raises(ValidationError):
        AIInterpretationCreate(**{**_VALID_CREATE, "generated_by": "gpt4"})


# ---------------------------------------------------------------------------
# Pydantic schema — AIInterpretationCreate: confidence bounds
# ---------------------------------------------------------------------------

def test_create_schema_accepts_confidence_zero():
    schema = AIInterpretationCreate(**{**_VALID_CREATE, "confidence": 0.0})
    assert schema.confidence == 0.0


def test_create_schema_accepts_confidence_one():
    schema = AIInterpretationCreate(**{**_VALID_CREATE, "confidence": 1.0})
    assert schema.confidence == 1.0


def test_create_schema_rejects_confidence_below_zero():
    with pytest.raises(ValidationError):
        AIInterpretationCreate(**{**_VALID_CREATE, "confidence": -0.01})


def test_create_schema_rejects_confidence_above_one():
    with pytest.raises(ValidationError):
        AIInterpretationCreate(**{**_VALID_CREATE, "confidence": 1.01})


# ---------------------------------------------------------------------------
# Pydantic schema — JSON field validators (string → parsed type)
# ---------------------------------------------------------------------------

def test_explainability_json_field_validator_parses_json_string():
    json_str = json.dumps(["reason 1", "reason 2"])
    schema = AIInterpretationCreate(**{**_VALID_CREATE, "explainability_json": json_str})
    assert isinstance(schema.explainability_json, list)
    assert schema.explainability_json[0] == "reason 1"


def test_source_snapshot_json_field_validator_parses_json_string():
    snapshot = {"kpis": [{"name": "avg_logins", "confidence": 0.92}]}
    json_str = json.dumps(snapshot)
    schema = AIInterpretationCreate(**{**_VALID_CREATE, "source_snapshot_json": json_str})
    assert isinstance(schema.source_snapshot_json, dict)
    assert "kpis" in schema.source_snapshot_json


def test_explainability_json_accepts_native_list():
    schema = AIInterpretationCreate(**_VALID_CREATE)
    assert isinstance(schema.explainability_json, list)


# ---------------------------------------------------------------------------
# Pydantic schema — AIInterpretationRead: ORM → schema round-trip
# ---------------------------------------------------------------------------

def test_read_schema_from_orm_model():
    now = datetime.utcnow()
    interp = AIInterpretation(
        id=42,
        entity_id="student_101",
        entity_type="student",
        dimension=InterpretationDimension.retention_risk,
        interpretation_version=2,
        confidence=0.91,
        risk_level=InterpretationRiskLevel.critical,
        summary="Critical dropout risk detected.",
        recommended_action="Immediate intervention required.",
        generated_by=InterpretationGeneratedBy.claude,
        model_name="claude-sonnet-4-6",
        created_at=now,
        updated_at=now,
        is_active=True,
    )
    schema = AIInterpretationRead.model_validate(interp)
    assert schema.id == 42
    assert schema.entity_id == "student_101"
    assert schema.risk_level == InterpretationRiskLevel.critical
    assert schema.confidence == 0.91
    assert schema.interpretation_version == 2
    assert schema.is_active is True
    assert schema.invalidated_at is None
    assert schema.invalidation_reason is None


def test_read_schema_invalidated_row_round_trips_correctly():
    now = datetime.utcnow()
    interp = AIInterpretation(
        id=10,
        entity_id="student_202",
        entity_type="student",
        dimension=InterpretationDimension.engagement,
        interpretation_version=1,
        confidence=0.0,
        risk_level=InterpretationRiskLevel.unknown,
        summary="Fallback — AI unavailable.",
        generated_by=InterpretationGeneratedBy.fallback,
        created_at=now,
        updated_at=now,
        invalidated_at=now,
        is_active=False,
        invalidation_reason="Superseded by claude interpretation id=11.",
    )
    schema = AIInterpretationRead.model_validate(interp)
    assert schema.is_active is False
    assert schema.invalidated_at == now
    assert schema.invalidation_reason == "Superseded by claude interpretation id=11."


# ---------------------------------------------------------------------------
# Pydantic schema — AIInterpretationInvalidate
# ---------------------------------------------------------------------------

def test_invalidate_schema_accepts_valid_reason():
    schema = AIInterpretationInvalidate(invalidation_reason="New KPI data changes risk profile.")
    assert schema.invalidation_reason == "New KPI data changes risk profile."


def test_invalidate_schema_rejects_empty_string():
    with pytest.raises(ValidationError):
        AIInterpretationInvalidate(invalidation_reason="")
