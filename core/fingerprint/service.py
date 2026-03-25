import json
from typing import Dict, Any

from sqlalchemy.orm import Session

from core.fingerprint.patterns import BehaviorPattern
from core.fingerprint.evaluator import FingerprintEvaluator
from services.models import BehaviorFingerprint


class FingerprintService:

    def __init__(self):
        self.evaluator = FingerprintEvaluator()

    def evaluate_and_store(
        self,
        db: Session,
        entity_type: str,
        entity_id: str,
        pattern: BehaviorPattern,
        metrics: Dict[str, Any],
    ) -> BehaviorFingerprint:

        result = self.evaluator.evaluate(pattern, metrics)

        record = BehaviorFingerprint(
            entity_type=entity_type,
            entity_id=entity_id,
            pattern_name=result.pattern_name,
            score=result.score,
            risk_level=result.risk_level,
            details_json=json.dumps(result.details),
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return record
