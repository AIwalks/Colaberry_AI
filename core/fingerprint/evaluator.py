from typing import Dict, Any

from core.fingerprint.patterns import BehaviorPattern, FingerprintResult


class FingerprintEvaluator:
    def evaluate(self, pattern: BehaviorPattern, metrics: Dict[str, Any]) -> FingerprintResult:
        matched = 0
        total = len(pattern.thresholds)

        for key, expected in pattern.thresholds.items():
            actual = metrics.get(key)

            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                if actual >= expected:
                    matched += 1
            else:
                if actual == expected:
                    matched += 1

        score = matched / total if total else 0.0

        if score >= 0.8:
            risk_level = "high"
        elif score >= 0.5:
            risk_level = "medium"
        else:
            risk_level = "low"

        return FingerprintResult(
            pattern_name=pattern.name,
            score=score,
            risk_level=risk_level,
            details={
                "matched": matched,
                "total": total,
                "metrics": metrics,
            },
        )
