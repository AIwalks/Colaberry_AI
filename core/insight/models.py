from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Insight:
    title: str
    body: str
    insight_type: str
    entity_type: str
    entity_id: int
    source_kpis: Dict[str, float]
    source_patterns: Dict[str, float]
    confidence: float


@dataclass
class InsightGenerationResult:
    insights: List[Insight]
    generated_count: int
    analyzed_kpis: int
    analyzed_fingerprints: int
