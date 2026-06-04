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
You are a student success advisor assistant. Your job is to interpret student engagement
data and write clear, professional summaries that help academic advisors take informed action.

Given student engagement signals and behavioral observations, return a single JSON object
with exactly these fields:

{
  "summary": "<one to two sentence plain-English description of what this student's engagement looks like right now>",
  "risk_level": "<one of: low | medium | high | critical>",
  "confidence": <float between 0.0 and 1.0>,
  "recommended_action": "<one specific, practical action an advisor should take this week>",
  "explainability": ["<observation 1>", "<observation 2>", "<observation 3>"]
}

Writing rules:
- Return ONLY the JSON object. No markdown, no code fences, no preamble, no trailing text.
- Write for an academic advisor, not a data scientist. Plain, professional language only.
- Use observable, specific language grounded in the numbers provided.
  Prefer: "No platform activity in 18 days" over "elevated disengagement risk detected".
- Refer to the student as "the student" or "this student". Never "entity" or "subject".
- explainability must contain 2 to 4 items. Each must cite a specific observed data point.
  Good: "No platform activity recorded in 18 days"
  Good: "0 of 5 advisor outreach attempts were completed by the student"
  Good: "Attendance rate is 71% — below the 80% threshold"
  Bad:  "Behavioral fingerprint indicates risk escalation"
  Bad:  "KPI signal threshold exceeded"
- Do NOT use these terms: behavioral fingerprint, trigger completion, risk escalation,
  KPI, entity, signal threshold, pipeline, sentinel, material change.
- confidence must reflect data completeness. Use lower confidence when signals are sparse
  or when many values are listed as not available.
- recommended_action must name a concrete next step: "Call the student this week to check in",
  not "Consider reaching out when appropriate".
- When data is incomplete, say so in recommended_action:
  "Limited data available — confirm enrollment status before outreach."
- Do NOT invent metrics. Do NOT infer GPA, grades, or academic outcomes not present in the data.
- Non-alarmist tone: prefer "reduced engagement" over "critical disengagement crisis".
- risk_level must be exactly one of: low, medium, high, critical.
""".strip()


# ---------------------------------------------------------------------------
# Label maps — translate internal field names into advisor-readable language
# ---------------------------------------------------------------------------

_KPI_LABEL_MAP: dict[str, tuple[str, str]] = {
    "last_activity_days":            ("Days since last platform activity",    "days"),
    "last_login_days":               ("Days since last login",                "days"),
    "past_10_days_logon":            ("Logins in the last 10 days",           "count"),
    "attendance_percentage":         ("Attendance rate",                      "percent"),
    "homeworks_behind":              ("Assignments currently behind",         "count"),
    "avg_hw_score":                  ("Average assignment score",             "score"),
    "avg_eff_rating":                ("Average effort rating",                "score"),
    "submission_rate":               ("Assignment submission rate",           "ratio"),
    "is_class_active":               ("Class enrollment status",              "bool"),
    "active_status":                 ("Student enrollment status",            "string"),
    "total_triggers_fired":          ("Total advisor outreach attempts",      "count"),
    "trigger_completion_rate":       ("Student response rate to outreach",    "ratio"),
    "inbound_message_count":         ("Messages received from student",       "count"),
    "outbound_message_count":        ("Messages sent to student",             "count"),
    "intervention_completion_rate":  ("Intervention completion rate",         "ratio"),
    "delivery_log_success_rate":     ("Message delivery success rate",        "ratio"),
    "positive_engagement_events":    ("Positive engagement events",           "count"),
    "days_in_status":                ("Days in current enrollment status",    "days"),
    "payment_balance":               ("Outstanding payment balance ($)",      "currency"),
    "total_payments":                ("Total payments recorded ($)",          "currency"),
}

_FP_LABEL_MAP: dict[str, str] = {
    "stale_login_pattern":     "No login activity recorded for an extended period",
    "stale_activity_pattern":  "No platform activity recorded for an extended period",
    "low_trigger_completion":  "Low student response rate to advisor outreach",
    "active_but_disconnected": "Enrolled and marked active but not engaging with the platform",
}


def _format_kpi_value(value: Any, unit: str) -> str:
    """Convert a raw KPI value + unit into a human-readable string."""
    if value is None:
        return "not available"
    try:
        if unit == "days":
            return f"{int(value)} days"
        if unit == "percent":
            return f"{float(value):.1f}%"
        if unit == "ratio":
            return f"{float(value) * 100:.0f}%"
        if unit == "bool":
            return "active" if value in (1, True, "1", "true", "True") else "inactive"
        if unit == "count":
            return str(int(float(value)))
        if unit in ("score", "currency"):
            return str(value)
    except (TypeError, ValueError):
        pass
    return str(value)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt(student_data: dict) -> str:
    """Format student engagement data into an advisor-readable prompt for Claude."""
    kpis: list         = student_data.get("kpis", [])
    fingerprints: list = student_data.get("fingerprints", [])
    entity_id: str     = str(student_data.get("entity_id", "unknown"))

    # Build engagement signal lines — include actual values so Claude can cite them.
    kpi_lines: list[str] = []
    null_count = 0
    for k in kpis:
        raw_name = k.get("kpi_name", "")
        value    = k.get("value")
        unit     = k.get("unit", "")
        conf     = float(k.get("confidence", 0.0))

        label, unit_hint = _KPI_LABEL_MAP.get(raw_name, (raw_name.replace("_", " ").title(), unit))
        formatted        = _format_kpi_value(value, unit or unit_hint)
        conf_label       = "high" if conf >= 0.8 else ("medium" if conf >= 0.5 else "low")
        if value is None:
            null_count += 1
        kpi_lines.append(f"  - {label}: {formatted} (data reliability: {conf_label})")

    if not kpi_lines:
        kpi_lines = ["  No engagement signals are available for this student."]

    # Translate internal pattern names into readable observations.
    fp_lines: list[str] = []
    for fp in fingerprints:
        raw_name  = fp.get("pattern_name", "unknown")
        risk      = fp.get("risk_level", "unknown")
        score     = float(fp.get("score", 0.0))
        label     = _FP_LABEL_MAP.get(raw_name, raw_name.replace("_", " ").capitalize())
        fp_lines.append(f"  - {label} (concern level: {risk}, severity: {score:.2f})")

    if not fp_lines:
        fp_lines = ["  No behavioral patterns flagged."]

    # Warn Claude when data is sparse so it can lower its confidence score.
    completeness_note = ""
    if kpis and null_count >= max(1, len(kpis) // 2):
        completeness_note = (
            f"\nData completeness note: {null_count} of {len(kpis)} signals are unavailable. "
            "Reflect this uncertainty in your confidence score and recommended action."
        )

    signal_block = "\n".join(kpi_lines)
    fp_block     = "\n".join(fp_lines)

    return (
        f"Student ID: {entity_id}\n\n"
        f"Engagement Signals:\n{signal_block}\n\n"
        f"Flagged Behavioral Observations:\n{fp_block}"
        f"{completeness_note}"
    )


def _call_claude(prompt: str, api_key: str) -> dict[str, Any]:
    # Deferred import — application boots normally if anthropic is not installed.
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=768,
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
