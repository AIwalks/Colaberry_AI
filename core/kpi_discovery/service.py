from typing import List, Dict, Any

from sqlalchemy.orm import Session

from services.models import BehaviorFingerprint, DiscoveredKPI

from core.kpi_discovery.analyzer import KPIDiscoveryAnalyzer


class KPIDiscoveryService:

    def __init__(self):
        self.analyzer = KPIDiscoveryAnalyzer()

    def load_fingerprints(
        self,
        db: Session,
    ) -> List[Dict[str, Any]]:

        rows = db.query(BehaviorFingerprint).all()

        result: List[Dict[str, Any]] = []

        for r in rows:
            result.append(
                {
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "pattern_name": r.pattern_name,
                    "metrics": {},
                }
            )

        return result

    def save_kpis(
        self,
        db,
        kpis,
    ):

        for k in kpis.values():

            row = DiscoveredKPI(
                kpi_name=k.kpi_name,
                source_pattern=k.source_pattern,
                entity_type=k.entity_type,
                formula=k.formula,
                confidence=k.confidence,
                sample_size=k.sample_size,
            )

            db.add(row)

        db.commit()

    def discover_kpis(
        self,
        db,
    ):

        fingerprints = self.load_fingerprints(db)

        result = self.analyzer.analyze(
            fingerprints=fingerprints,
        )

        self.save_kpis(
            db,
            result.kpis,
        )

        return result
