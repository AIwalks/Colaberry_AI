from typing import List, Dict, Any, TYPE_CHECKING

from sqlalchemy.orm import Session

from core.insight.generator import InsightGenerator
from core.insight.models import InsightGenerationResult

from services.models import BehaviorFingerprint, DiscoveredKPI

if TYPE_CHECKING:
    from services.models import GeneratedInsight


class InsightService:

    def load_kpis(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
    ) -> List[Dict[str, Any]]:

        rows = (
            db.query(DiscoveredKPI)
            .filter(
                DiscoveredKPI.entity_type == entity_type,
            )
            .all()
        )

        result: List[Dict[str, Any]] = []

        for r in rows:
            result.append(
                {
                    "kpi_name": r.kpi_name,
                    "source_pattern": r.source_pattern,
                    "entity_type": r.entity_type,
                    "formula": r.formula,
                    "confidence": r.confidence,
                    "sample_size": r.sample_size,
                }
            )

        return result

    def load_fingerprints(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
    ) -> List[Dict[str, Any]]:

        rows = (
            db.query(BehaviorFingerprint)
            .filter(
                BehaviorFingerprint.entity_id == entity_id,
                BehaviorFingerprint.entity_type == entity_type,
            )
            .all()
        )

        result: List[Dict[str, Any]] = []

        for r in rows:
            result.append(
                {
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "pattern_name": r.pattern_name,
                    "score": r.score,
                    "risk_level": r.risk_level,
                }
            )

        return result

    def save_insights(
        self,
        db: Session,
        insights: List,
    ) -> None:

        from services.models import GeneratedInsight

        for insight in insights:
            exists = (
                db.query(GeneratedInsight.id)
                .filter(
                    GeneratedInsight.insight_type == insight.insight_type,
                    GeneratedInsight.entity_type  == insight.entity_type,
                    GeneratedInsight.entity_id    == str(insight.entity_id),
                    GeneratedInsight.title        == insight.title,
                )
                .first()
            )
            if exists:
                continue

            row = GeneratedInsight(
                title=insight.title,
                body=insight.body,
                insight_type=insight.insight_type,
                entity_type=insight.entity_type,
                entity_id=str(insight.entity_id),
                confidence=insight.confidence,
            )
            db.add(row)

        db.commit()

    def generate_insights(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
    ) -> InsightGenerationResult:

        kpis = self.load_kpis(db, entity_id=entity_id, entity_type=entity_type)

        fingerprints = self.load_fingerprints(db, entity_id=entity_id, entity_type=entity_type)

        generator = InsightGenerator()

        result = generator.generate_insights(
            kpis,
            fingerprints,
            entity_id=entity_id,
            entity_type=entity_type,
        )

        self.save_insights(
            db,
            result.insights,
        )

        response_insights = []

        for i, ins in enumerate(result.insights, start=1):
            response_insights.append({
                "id": i,
                "title": ins.title,
                "body": ins.body,
                "insight_type": ins.insight_type,
                "entity_type": ins.entity_type,
                "entity_id": str(ins.entity_id),
                "confidence": ins.confidence,
                "explanation": ins.explanation,
                "recommended_action": ins.recommended_action,
            })

        return {
            "generated_count": len(response_insights),
            "analyzed_kpis": result.analyzed_kpis,
            "analyzed_fingerprints": result.analyzed_fingerprints,
            "insights": response_insights,
        }
