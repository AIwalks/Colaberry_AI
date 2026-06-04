from pydantic import BaseModel
from typing import List, Optional


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
    explanation: Optional[str] = None
    recommended_action: Optional[str] = None


class InsightGenerateResponse(BaseModel):
    generated_count: int
    analyzed_kpis: int
    analyzed_fingerprints: int
    insights: List[InsightResponse]


class AIInsightResponse(BaseModel):
    id: int
    title: str
    body: str
    insight_type: str
    entity_type: str
    entity_id: str
    confidence: float
    explanation: Optional[str] = None
    recommended_action: Optional[str] = None
    risk_level: str
    explainability: List[str]


class AIInsightGenerateResponse(BaseModel):
    ai_enabled: bool
    entity_id: str
    entity_type: str
    analyzed_kpis: int
    analyzed_fingerprints: int
    insights: List[AIInsightResponse]
    message: Optional[str] = None
