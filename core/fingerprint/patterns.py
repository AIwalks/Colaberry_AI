from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class BehaviorPattern:
    name: str
    description: str
    thresholds: Dict[str, Any]


@dataclass
class FingerprintResult:
    pattern_name: str
    score: float
    risk_level: str
    details: Dict[str, Any]
