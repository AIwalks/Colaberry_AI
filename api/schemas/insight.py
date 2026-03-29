from pydantic import BaseModel
from typing import List


class InsightGenerateRequest(BaseModel):
    entity_id: str
    entity_type: str


class InsightResponse(BaseModel):
    id: int
    title: str
    body: str
    insight_type: str
    entity_type: str
    entity_id: str
    confidence: float


class InsightGenerateResponse(BaseModel):
    generated_count: int
    analyzed_kpis: int
    analyzed_fingerprints: int
    insights: List[InsightResponse]
