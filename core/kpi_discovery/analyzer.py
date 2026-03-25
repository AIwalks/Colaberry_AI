from typing import List, Dict, Any

from core.kpi_discovery.models import (
    DiscoveredKPI,
    KPIDiscoveryResult,
)


class KPIDiscoveryAnalyzer:

    def analyze(
        self,
        fingerprints: List[Dict[str, Any]],
    ) -> KPIDiscoveryResult:

        kpis: Dict[str, DiscoveredKPI] = {}

        total = len(fingerprints)

        if total == 0:
            return KPIDiscoveryResult(
                kpis={},
                analyzed_count=0,
                metadata={},
            )

        login_values = [
            f.get("metrics", {}).get("logins", 0)
            for f in fingerprints
        ]

        avg_logins = sum(login_values) / total

        kpi = DiscoveredKPI(
            kpi_name="avg_logins",
            source_pattern="auto",
            entity_type="student",
            formula="avg(logins)",
            confidence=0.8,
            sample_size=total,
        )

        kpis["avg_logins"] = kpi

        return KPIDiscoveryResult(
            kpis=kpis,
            analyzed_count=total,
            metadata={
                "avg_logins": avg_logins,
            },
        )
