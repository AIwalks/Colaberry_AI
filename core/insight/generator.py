from typing import List, Dict, Any

from core.insight.models import Insight, InsightGenerationResult


class InsightGenerator:

    def generate_insights(
        self,
        kpis: List[Dict[str, Any]],
        fingerprints: List[Dict[str, Any]],
    ) -> InsightGenerationResult:

        insights: List[Insight] = []

        for kpi in kpis:
            if kpi.get("confidence", 0.0) > 0.7:
                insights.append(
                    Insight(
                        title=f"High-confidence KPI: {kpi.get('kpi_name', 'unknown')}",
                        body=(
                            f"KPI '{kpi.get('kpi_name')}' has confidence "
                            f"{kpi.get('confidence')} for entity type "
                            f"'{kpi.get('entity_type')}'."
                        ),
                        insight_type="kpi",
                        entity_type=kpi.get("entity_type", ""),
                        entity_id=kpi.get("entity_id", 0),
                        source_kpis={kpi.get("kpi_name", ""): kpi.get("confidence", 0.0)},
                        source_patterns={},
                        confidence=kpi.get("confidence", 0.0),
                    )
                )

        for fp in fingerprints:
            if fp.get("risk_level") == "high":
                insights.append(
                    Insight(
                        title=f"High-risk pattern: {fp.get('pattern_name', 'unknown')}",
                        body=(
                            f"Entity '{fp.get('entity_id')}' of type "
                            f"'{fp.get('entity_type')}' shows high-risk pattern "
                            f"'{fp.get('pattern_name')}'."
                        ),
                        insight_type="risk",
                        entity_type=fp.get("entity_type", ""),
                        entity_id=fp.get("entity_id", 0),
                        source_kpis={},
                        source_patterns={fp.get("pattern_name", ""): fp.get("score", 0.0)},
                        confidence=fp.get("score", 0.0),
                    )
                )

        return InsightGenerationResult(
            insights=insights,
            generated_count=len(insights),
            analyzed_kpis=len(kpis),
            analyzed_fingerprints=len(fingerprints),
        )
