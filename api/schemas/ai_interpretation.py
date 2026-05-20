"""Pydantic schemas for AIInterpretation.

These schemas validate and serialize data in/out of the AIInterpretation ORM model.
They do not own database I/O — callers load and persist via the ORM.

JSON storage note
─────────────────
explainability_json and source_snapshot_json are stored as Text (JSON strings) in
the database. The field validators below accept both the raw JSON string (as returned
by a DB read) and the already-parsed Python type (as provided by the AI service).
Callers writing to the ORM must serialize with json.dumps before assigning.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from services.models import (
    InterpretationDimension,
    InterpretationGeneratedBy,
    InterpretationRiskLevel,
)


class AIInterpretationCreate(BaseModel):
    entity_id:              str
    entity_type:            str
    dimension:              InterpretationDimension
    interpretation_version: int                      = 1
    confidence:             float                    = Field(ge=0.0, le=1.0)
    risk_level:             InterpretationRiskLevel
    summary:                str
    recommended_action:     Optional[str]            = None
    explainability_json:    Optional[List[str]]      = None
    source_metrics_hash:    Optional[str]            = None
    source_snapshot_json:   Optional[Dict[str, Any]] = None
    generated_by:           InterpretationGeneratedBy
    model_name:             Optional[str]            = None

    @field_validator("explainability_json", mode="before")
    @classmethod
    def parse_explainability_json(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("source_snapshot_json", mode="before")
    @classmethod
    def parse_source_snapshot_json(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v)
        return v


class AIInterpretationRead(AIInterpretationCreate):
    id:                  int
    created_at:          datetime
    updated_at:          datetime
    invalidated_at:      Optional[datetime] = None
    stale_after:         Optional[datetime] = None
    is_active:           bool
    invalidation_reason: Optional[str]      = None

    model_config = {"from_attributes": True}


class AIInterpretationInvalidate(BaseModel):
    invalidation_reason: str = Field(min_length=1)
