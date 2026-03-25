from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class DiscoveredKPI:
    kpi_name: str
    source_pattern: str
    entity_type: str
    formula: str
    confidence: float
    sample_size: int


@dataclass
class KPIDiscoveryResult:
    kpis: Dict[str, DiscoveredKPI]
    analyzed_count: int
    metadata: Dict[str, Any]
