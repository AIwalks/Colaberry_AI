"""Material Change Evaluation Service.

Determines whether an existing AIInterpretation can be safely reused or whether
a new interpretation must be generated.

This service is called before any Claude API invocation. It is entirely
deterministic: no probabilistic inference, no external API calls, no database
writes, no side effects. The same inputs always produce the same output.

Why this exists before the AI layer
────────────────────────────────────
AI inference is expensive (tokens), probabilistic (same input → slightly different
output across calls), and slow (network latency). Calling Claude on every poll cycle
— regardless of whether the student's data has materially changed — would produce
unstable governance artifacts, inflate token costs, and make interpretation records
untrustworthy as audit evidence.

This service is the gate: only material state changes pass through to Claude.

Decision output contract
────────────────────────
evaluate_material_change() always returns a dict with exactly these keys:

  reuse_existing          bool   — safe to return the existing interpretation
  generate_new            bool   — a new interpretation must be created
  invalidate_existing     bool   — the existing record should be marked inactive
  reason                  str    — human-readable audit string
  severity                str    — "none" | "low" | "medium" | "high"
  confidence_delta        float | None
  risk_changed            bool
  new_fingerprint_detected bool

Exactly one of (reuse_existing, generate_new) is True.
invalidate_existing is True only when generate_new=True and a live prior
interpretation exists.

V1 rule summary
────────────────
RULE 1  Confidence delta > 0.20 between KPI aggregate and prior interpretation
RULE 2  Risk escalation: prior risk < current inferred risk (upward only)
RULE 3  New behavioral fingerprint not present in the prior source snapshot
RULE 4  Interpretation past its stale_after timestamp
RULE 5  Cross-dimension deterioration: 2+ fingerprints at high or critical risk
RULE 6  No material change → reuse (default when all other rules pass)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONFIDENCE_DELTA_THRESHOLD: float = 0.20
_CROSS_DIMENSION_THRESHOLD: int = 2  # number of high/critical fingerprints to trigger Rule 5

_RISK_RANK: dict[str, int] = {
    "unknown":  -1,
    "low":       0,
    "medium":    1,
    "high":      2,
    "critical":  3,
}

_DETERIORATION_RISK_FLOOR = _RISK_RANK["high"]  # Rule 5 counts fingerprints at this rank or above


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MaterialChangeEvaluationService:
    """Evaluates whether an existing AI interpretation can be reused.

    All public and private methods are pure functions over their arguments.
    No database session is opened. The latest_interpretation parameter accepts
    any object with the expected attributes (AIInterpretation ORM instance or
    any compatible stub), enabling deterministic unit testing without fixtures.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_material_change(
        self,
        entity_id: str,
        entity_type: str,
        dimension: str,
        current_kpis: list[dict[str, Any]],
        current_fingerprints: list[dict[str, Any]],
        latest_interpretation: Optional[Any],
    ) -> dict[str, Any]:
        """Evaluate whether a new AI interpretation should be generated.

        Parameters
        ----------
        entity_id, entity_type, dimension
            Identity of the assessment being evaluated.
        current_kpis
            List of KPI dicts from InsightService.load_kpis().
            Each dict must contain at least: kpi_name (str), confidence (float).
        current_fingerprints
            List of fingerprint dicts from InsightService.load_fingerprints().
            Each dict must contain at least: pattern_name (str), risk_level (str).
        latest_interpretation
            The most recent AIInterpretation for this entity/dimension, or None.
            Accessed via getattr to avoid hard ORM coupling.
        """
        # No prior interpretation → must generate
        if latest_interpretation is None:
            return self._decide_generate(
                reason=(
                    f"No existing interpretation found for entity_id={entity_id!r}, "
                    f"entity_type={entity_type!r}, dimension={dimension!r}."
                ),
                severity="medium",
                confidence_delta=None,
                risk_changed=False,
                new_fingerprint_detected=False,
                has_active_prior=False,
            )

        has_active_prior = bool(getattr(latest_interpretation, "is_active", False))

        # ---- RULE 4: Stale -----------------------------------------------
        if self._is_stale(latest_interpretation):
            stale_after = getattr(latest_interpretation, "stale_after", None)
            return self._decide_generate(
                reason=(
                    f"Interpretation id={getattr(latest_interpretation, 'id', None)} "
                    f"is stale: stale_after={stale_after}, "
                    f"evaluated_at={datetime.utcnow().isoformat()}."
                ),
                severity="medium",
                confidence_delta=None,
                risk_changed=False,
                new_fingerprint_detected=False,
                has_active_prior=has_active_prior,
            )

        # ---- RULE 2: Risk escalation -------------------------------------
        current_risk = self._infer_current_risk(current_fingerprints)
        prior_risk = str(getattr(latest_interpretation, "risk_level", "unknown"))
        if self._is_risk_escalation(current_risk, prior_risk):
            return self._decide_generate(
                reason=(
                    f"Risk escalation detected: prior_risk={prior_risk!r} → "
                    f"current_inferred_risk={current_risk!r} "
                    f"(entity_id={entity_id!r}, dimension={dimension!r})."
                ),
                severity="high",
                confidence_delta=None,
                risk_changed=True,
                new_fingerprint_detected=False,
                has_active_prior=has_active_prior,
            )

        # ---- RULE 3: New fingerprint -------------------------------------
        prior_fp_names = self._get_prior_fingerprint_names(latest_interpretation)
        new_fps = self._detect_new_fingerprints(current_fingerprints, prior_fp_names)
        if new_fps:
            return self._decide_generate(
                reason=(
                    f"New behavioral fingerprint(s) detected absent from prior snapshot: "
                    f"{sorted(new_fps)!r} (entity_id={entity_id!r})."
                ),
                severity="medium",
                confidence_delta=None,
                risk_changed=False,
                new_fingerprint_detected=True,
                has_active_prior=has_active_prior,
            )

        # ---- RULE 5: Cross-dimension deterioration -----------------------
        if self._has_cross_dimension_deterioration(current_fingerprints):
            deteriorated_patterns = sorted(
                fp.get("pattern_name", "unknown")
                for fp in current_fingerprints
                if _RISK_RANK.get(fp.get("risk_level", "unknown"), -1) >= _DETERIORATION_RISK_FLOOR
            )
            return self._decide_generate(
                reason=(
                    f"Cross-dimension deterioration: {len(deteriorated_patterns)} fingerprint(s) "
                    f"at high or critical risk: {deteriorated_patterns!r} "
                    f"(entity_id={entity_id!r})."
                ),
                severity="high",
                confidence_delta=None,
                risk_changed=False,
                new_fingerprint_detected=False,
                has_active_prior=has_active_prior,
            )

        # ---- RULE 1: Confidence delta ------------------------------------
        prior_confidence = getattr(latest_interpretation, "confidence", None)
        delta = self._compute_confidence_delta(current_kpis, prior_confidence)
        if delta is not None and delta > _CONFIDENCE_DELTA_THRESHOLD:
            current_agg = self._aggregate_confidence(current_kpis)
            return self._decide_generate(
                reason=(
                    f"Confidence delta {delta:.3f} exceeds threshold "
                    f"{_CONFIDENCE_DELTA_THRESHOLD}: prior_confidence={prior_confidence:.3f}, "
                    f"current_aggregate={current_agg:.3f} "
                    f"(entity_id={entity_id!r}, dimension={dimension!r})."
                ),
                severity="low",
                confidence_delta=delta,
                risk_changed=False,
                new_fingerprint_detected=False,
                has_active_prior=has_active_prior,
            )

        # ---- RULE 6: No material change — reuse --------------------------
        return {
            "reuse_existing":           True,
            "generate_new":             False,
            "invalidate_existing":      False,
            "reason": (
                f"No material change detected for entity_id={entity_id!r}, "
                f"dimension={dimension!r}. Interpretation "
                f"id={getattr(latest_interpretation, 'id', None)} "
                f"is current and actionable."
            ),
            "severity":                 "none",
            "confidence_delta":         delta,
            "risk_changed":             False,
            "new_fingerprint_detected": False,
        }

    # ------------------------------------------------------------------
    # Rule helpers
    # ------------------------------------------------------------------

    def _is_stale(self, interpretation: Any) -> bool:
        """Rule 4: True if stale_after is set and has passed."""
        stale_after = getattr(interpretation, "stale_after", None)
        if stale_after is None:
            return False
        return stale_after < datetime.utcnow()

    def _infer_current_risk(self, fingerprints: list[dict[str, Any]]) -> str:
        """Return the highest risk_level across current fingerprints.

        Used by Rule 2 as a proxy for the current risk state before Claude runs.
        Returns 'unknown' when no fingerprints are present.
        """
        if not fingerprints:
            return "unknown"
        max_rank = -1
        max_risk = "unknown"
        for fp in fingerprints:
            rl = str(fp.get("risk_level", "unknown"))
            rank = _RISK_RANK.get(rl, -1)
            if rank > max_rank:
                max_rank = rank
                max_risk = rl
        return max_risk

    def _is_risk_escalation(self, current_risk: str, prior_risk: str) -> bool:
        """Rule 2: True only when risk has increased. De-escalation does not trigger."""
        return _RISK_RANK.get(current_risk, -1) > _RISK_RANK.get(prior_risk, -1)

    def _get_prior_fingerprint_names(self, interpretation: Any) -> set[str]:
        """Extract fingerprint pattern names from the interpretation's source snapshot.

        The snapshot is stored as a JSON string in source_snapshot_json.
        Expected shape: {"fingerprints": [{"pattern_name": "..."}, ...]}
        Returns empty set when snapshot is absent or unparseable.
        """
        snapshot_raw = getattr(interpretation, "source_snapshot_json", None)
        if not snapshot_raw:
            return set()
        try:
            snapshot = (
                json.loads(snapshot_raw)
                if isinstance(snapshot_raw, str)
                else snapshot_raw
            )
            fps = snapshot.get("fingerprints", [])
            return {fp["pattern_name"] for fp in fps if fp.get("pattern_name")}
        except (json.JSONDecodeError, AttributeError, TypeError):
            logger.warning(
                "Could not parse source_snapshot_json for fingerprint comparison; "
                "treating prior fingerprint set as empty."
            )
            return set()

    def _detect_new_fingerprints(
        self,
        current_fingerprints: list[dict[str, Any]],
        prior_names: set[str],
    ) -> set[str]:
        """Rule 3: Return pattern names present in current data but absent from the prior snapshot.

        Returns empty set when prior_names is empty — absence of a snapshot means
        we cannot determine novelty, so we do not trigger on this rule alone.
        """
        if not prior_names:
            return set()
        current_names = {
            fp["pattern_name"]
            for fp in current_fingerprints
            if fp.get("pattern_name")
        }
        return current_names - prior_names

    def _has_cross_dimension_deterioration(
        self, fingerprints: list[dict[str, Any]]
    ) -> bool:
        """Rule 5: True when 2 or more fingerprints are at high or critical risk."""
        count = sum(
            1
            for fp in fingerprints
            if _RISK_RANK.get(str(fp.get("risk_level", "unknown")), -1)
            >= _DETERIORATION_RISK_FLOOR
        )
        return count >= _CROSS_DIMENSION_THRESHOLD

    def _aggregate_confidence(
        self, kpis: list[dict[str, Any]]
    ) -> Optional[float]:
        """Mean confidence across all KPI signals. Returns None when no KPIs present."""
        if not kpis:
            return None
        values = [float(kpi.get("confidence", 0.0)) for kpi in kpis]
        return sum(values) / len(values)

    def _compute_confidence_delta(
        self,
        current_kpis: list[dict[str, Any]],
        prior_confidence: Optional[float],
    ) -> Optional[float]:
        """Rule 1: Absolute delta between current KPI aggregate and prior interpretation confidence.

        Returns None when either side is unavailable.
        """
        if prior_confidence is None:
            return None
        current_agg = self._aggregate_confidence(current_kpis)
        if current_agg is None:
            return None
        return abs(current_agg - prior_confidence)

    # ------------------------------------------------------------------
    # Decision builder
    # ------------------------------------------------------------------

    def _decide_generate(
        self,
        reason: str,
        severity: str,
        confidence_delta: Optional[float],
        risk_changed: bool,
        new_fingerprint_detected: bool,
        has_active_prior: bool,
    ) -> dict[str, Any]:
        return {
            "reuse_existing":           False,
            "generate_new":             True,
            "invalidate_existing":      has_active_prior,
            "reason":                   reason,
            "severity":                 severity,
            "confidence_delta":         confidence_delta,
            "risk_changed":             risk_changed,
            "new_fingerprint_detected": new_fingerprint_detected,
        }
