from pydantic import BaseModel
from typing import Dict, Any


class FingerprintRequest(BaseModel):
    entity_type: str
    entity_id: str
    pattern_name: str
    thresholds: Dict[str, Any]
    metrics: Dict[str, Any]


class FingerprintResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    pattern_name: str
    score: float
    risk_level: str
    details_json: str
