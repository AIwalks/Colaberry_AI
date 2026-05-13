"""Additive AI insight layer — isolated from the existing orchestration pipeline.

Accepts pre-computed KPI and fingerprint data, calls the Anthropic Claude API,
and returns a structured, explainable insight dict.

Intentional isolation constraints:
  - No ORM imports
  - No database access
  - No dependency on any existing service class
  - Not wired into any production route

To activate: import generate_ai_insight() from a new route or service.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fallback — returned on any failure path. confidence=0.0 and
# risk_level="unknown" make it machine-detectable as non-AI output.
# ---------------------------------------------------------------------------
_FALLBACK: dict[str, Any] = {
    "summary": "AI insight unavailable. Review KPI data manually.",
    "risk_level": "unknown",
    "confidence": 0.0,
    "recommended_action": "Manual review required — AI service did not return a result.",
    "explainability": ["AI service unavailable — this is a safe fallback response."],
}

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """
You are an educational analytics AI embedded in a student engagement monitoring system.

Given student KPI signals and behavioral fingerprint data, return a single JSON object
with exactly these fields:

{
  "summary": "<one to two sentence plain-English summary of the student's current state>",
  "risk_level": "<one of: low | medium | high | critical>",
  "confidence": <float between 0.0 and 1.0>,
  "recommended_action": "<specific, actionable recommendation for a mentor or advisor>",
  "explainability": ["<reason 1>", "<reason 2>", "<reason 3>"]
}

Rules:
- Return ONLY the JSON object. No markdown, no code fences, no preamble, no trailing text.
- explainability must contain 2 to 4 specific reasons drawn directly from the input data.
- confidence must reflect how strongly the input data supports the stated risk_level.
- recommended_action must be specific to this student's signals, not generic advice.
- risk_level must be exactly one of: low, medium, high, critical.
""".strip()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt(student_data: dict) -> str:
    """Format student KPI and fingerprint data into a structured user prompt."""
    kpis: list = student_data.get("kpis", [])
    fingerprints: list = student_data.get("fingerprints", [])
    entity_id: str = str(student_data.get("entity_id", "unknown"))
    entity_type: str = str(student_data.get("entity_type", "student"))

    kpi_lines = "\n".join(
        f"  - {k.get('kpi_name', 'unnamed')}: "
        f"confidence={k.get('confidence', 0):.2f}, "
        f"pattern={k.get('source_pattern', 'none')}, "
        f"sample_size={k.get('sample_size', 0)}"
        for k in kpis
    ) or "  None available."

    fp_lines = "\n".join(
        f"  - pattern={f.get('pattern_name', 'unknown')}, "
        f"risk_level={f.get('risk_level', 'unknown')}, "
        f"score={f.get('score', 0):.2f}"
        for f in fingerprints
    ) or "  None available."

    return (
        f"Entity type: {entity_type}\n"
        f"Entity ID:   {entity_id}\n\n"
        f"KPI Signals:\n{kpi_lines}\n\n"
        f"Behavioral Fingerprints:\n{fp_lines}"
    )


def _call_claude(prompt: str, api_key: str) -> dict[str, Any]:
    # Deferred import — application boots normally if anthropic is not installed.
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    return json.loads(raw)


def _validate(result: dict[str, Any]) -> dict[str, Any]:
    """Verify the response has the required shape before returning to caller."""
    required = {"summary", "risk_level", "confidence", "recommended_action", "explainability"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"Claude response missing required fields: {missing}")
    if not isinstance(result["explainability"], list):
        raise ValueError("explainability must be a list")
    valid_risk_levels = {"low", "medium", "high", "critical"}
    if result["risk_level"] not in valid_risk_levels:
        raise ValueError(f"risk_level '{result['risk_level']}' not in {valid_risk_levels}")
    result["confidence"] = float(result["confidence"])
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_ai_insight(student_data: dict) -> dict[str, Any]:
    """Generate a structured AI insight from student KPI and fingerprint data.

    Args:
        student_data: Dict with keys:
            entity_id   (str)  — student identifier
            entity_type (str)  — e.g. "student"
            kpis        (list) — list of KPI dicts from InsightService.load_kpis()
            fingerprints(list) — list of fingerprint dicts from InsightService.load_fingerprints()

    Returns:
        Dict with keys: summary, risk_level, confidence,
        recommended_action, explainability.

    Never raises. Returns _FALLBACK on any failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — returning fallback insight.")
        return _FALLBACK.copy()

    prompt = _build_prompt(student_data)

    try:
        result = _call_claude(prompt, api_key)
        return _validate(result)
    except ImportError:
        logger.error(
            "anthropic package not installed. "
            "Run: pip install anthropic"
        )
    except json.JSONDecodeError as exc:
        logger.error("Claude returned non-JSON response: %s", exc)
    except ValueError as exc:
        logger.error("Claude response failed validation: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error calling Claude API: %s", exc)

    return _FALLBACK.copy()
