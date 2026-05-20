"""Pydantic schemas for GovernanceReview.

Validate and serialize data in/out of the GovernanceReview ORM model.
These schemas do not own database I/O — callers load and persist via the ORM.

Schema hierarchy
────────────────
GovernanceReviewCreate   — fields required to open a new review
GovernanceReviewRead     — ORM → API response (includes id, timestamps, status)
GovernanceReviewApprove  — payload to approve a pending review
GovernanceReviewReject   — payload to reject a pending review (review_notes required)
GovernanceReviewDefer    — payload to defer a pending review (governance_reason required)
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from services.models import GovernanceReviewStatus


class GovernanceReviewCreate(BaseModel):
    interpretation_id:   int
    entity_id:           str
    entity_type:         str
    risk_level:          str
    confidence:          float                    = Field(ge=0.0, le=1.0)
    governance_reason:   str                      = Field(min_length=1)
    audit_snapshot_json: Optional[Dict[str, Any]] = None

    @field_validator("audit_snapshot_json", mode="before")
    @classmethod
    def parse_audit_snapshot(cls, v: Any) -> Any:
        import json
        if isinstance(v, str):
            return json.loads(v)
        return v


class GovernanceReviewRead(BaseModel):
    id:                  int
    created_at:          datetime
    updated_at:          datetime
    interpretation_id:   int
    entity_id:           str
    entity_type:         str
    status:              GovernanceReviewStatus
    reviewed_by:         Optional[str]            = None
    reviewed_at:         Optional[datetime]        = None
    review_notes:        Optional[str]             = None
    governance_reason:   str
    risk_level:          str
    confidence:          float
    audit_snapshot_json: Optional[Dict[str, Any]] = None
    is_active:           bool

    model_config = {"from_attributes": True}

    @field_validator("audit_snapshot_json", mode="before")
    @classmethod
    def parse_audit_snapshot(cls, v: Any) -> Any:
        import json
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v


class GovernanceReviewApprove(BaseModel):
    reviewed_by:  str          = Field(min_length=1)
    review_notes: Optional[str] = None


class GovernanceReviewReject(BaseModel):
    reviewed_by:  str = Field(min_length=1)
    review_notes: str = Field(min_length=1)


class GovernanceReviewDefer(BaseModel):
    reviewed_by:       str = Field(min_length=1)
    governance_reason: str = Field(min_length=1)
