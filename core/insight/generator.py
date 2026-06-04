from typing import Any, Dict, List, Optional

from core.insight.models import Insight, InsightGenerationResult
from skills.insight_explainer import generate_explanation

# ---------------------------------------------------------------------------
# KPI interpretation layer — deterministic, value-aware severity rules
# ---------------------------------------------------------------------------

def interpret_kpi(
    kpi_name: str,
    value: Any,
    unit: str,
) -> Dict[str, Any]:
    """Return severity, advisor-ready title/body/action, and suppress flag.

    suppress=True  → healthy signal; caller should skip generating an insight.
    suppress=False → concerning signal; caller uses the returned text.

    Unknown kpi_name falls back to suppress=False with a generic label so the
    existing behaviour for unmapped signals is preserved unchanged.
    """
    # Coerce value to float for threshold comparisons; preserve original for text.
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _fallback_kpi(kpi_name, value)

    if kpi_name == "attendance_percentage":
        return _interp_attendance(v)
    if kpi_name == "last_activity_days":
        return _interp_days_inactive(v, "platform activity")
    if kpi_name == "last_login_days":
        return _interp_days_inactive(v, "login")
    if kpi_name == "homeworks_behind":
        return _interp_homeworks_behind(v)
    if kpi_name == "avg_hw_score":
        return _interp_avg_hw_score(v)
    if kpi_name in ("submission_rate", "assignment_submission_rate"):
        return _interp_submission_rate(v)
    if kpi_name == "trigger_completion_rate":
        return _interp_completion_rate(
            v,
            label="outreach",
            healthy_threshold=0.60,
            warning_threshold=0.40,
            elevated_threshold=0.25,
        )
    if kpi_name == "intervention_completion_rate":
        return _interp_completion_rate(
            v,
            label="intervention",
            # Interventions are higher-stakes; healthy bar is raised to 0.70.
            healthy_threshold=0.70,
            warning_threshold=0.50,
            elevated_threshold=0.25,
        )
    return _fallback_kpi(kpi_name, value)


# ---------------------------------------------------------------------------
# Per-KPI interpreters
# ---------------------------------------------------------------------------

def _interp_attendance(v: float) -> Dict[str, Any]:
    pct = f"{v * 100:.0f}%"
    # ≥90% → healthy; 75–89% → warning; 50–74% → elevated; <50% → critical
    if v >= 0.90:
        return {"severity": "healthy", "suppress": True,
                "title": "", "body": "", "recommended_action": ""}
    if v >= 0.75:
        return {
            "severity": "warning",
            "suppress": False,
            "title": f"Attendance has dropped to {pct}",
            "body": (
                f"This student is attending {pct} of scheduled sessions — "
                f"below the 90% benchmark. Sessions are being missed regularly."
            ),
            "recommended_action": (
                "Note attendance at the next touchpoint. Ask whether scheduling, "
                "workload, or personal circumstances are creating barriers."
            ),
        }
    if v >= 0.50:
        return {
            "severity": "elevated",
            "suppress": False,
            "title": f"Low attendance — {pct} of sessions attended",
            "body": (
                f"Attendance is at {pct}, below the 75% threshold that "
                f"historically precedes disengagement. More sessions are being "
                f"missed than is safe for sustained progress."
            ),
            "recommended_action": (
                "Reach out directly this week to understand attendance barriers "
                "and create a concrete attendance recovery plan with the student."
            ),
        }
    # Critical: <50%
    return {
        "severity": "critical",
        "suppress": False,
        "title": f"Critical attendance — only {pct} of sessions attended",
        "body": (
            f"Attendance is at {pct}. This student is absent more often than "
            f"present and is at immediate risk of falling too far behind to recover."
        ),
        "recommended_action": (
            "Escalate immediately. Confirm the student is still enrolled and "
            "intends to continue. A formal attendance intervention is required "
            "before the next session."
        ),
    }


def _interp_days_inactive(v: float, activity_label: str) -> Dict[str, Any]:
    days = int(v)
    day_word = "day" if days == 1 else "days"
    # 0–3 → healthy; 4–7 → warning; 8–13 → elevated; ≥14 → critical
    if days <= 3:
        return {"severity": "healthy", "suppress": True,
                "title": "", "body": "", "recommended_action": ""}
    if days <= 7:
        return {
            "severity": "warning",
            "suppress": False,
            "title": f"No {activity_label} in {days} {day_word}",
            "body": (
                f"No {activity_label} recorded in {days} {day_word}. "
                f"This week-long gap may indicate the student is falling "
                f"out of their usual routine."
            ),
            "recommended_action": (
                f"Monitor for 3–4 more days. Send a light check-in message "
                f"if the gap continues."
            ),
        }
    if days <= 13:
        return {
            "severity": "elevated",
            "suppress": False,
            "title": f"No {activity_label} in {days} {day_word}",
            "body": (
                f"No {activity_label} recorded in {days} {day_word} — "
                f"a multi-week gap that frequently precedes disengagement."
            ),
            "recommended_action": (
                f"Proactively reach out to confirm the student has no access "
                f"barriers and is aware of upcoming deadlines."
            ),
        }
    # Critical: ≥14 days — aligns with FingerprintGeneratorService stale threshold
    return {
        "severity": "critical",
        "suppress": False,
        "title": f"No {activity_label} in {days} {day_word}",
        "body": (
            f"No {activity_label} recorded in {days} {day_word}. "
            f"This student meets the threshold for disengagement review "
            f"and requires immediate personal outreach."
        ),
        "recommended_action": (
            "Direct personal contact (phone or video call) required this week. "
            "Do not rely on automated messaging alone. Document the outcome."
        ),
    }


def _interp_homeworks_behind(v: float) -> Dict[str, Any]:
    n = int(v)
    hw_word = "assignment" if n == 1 else "assignments"
    # 0 → healthy; 1–2 → warning; 3–4 → elevated; ≥5 → critical
    if n == 0:
        return {"severity": "healthy", "suppress": True,
                "title": "", "body": "", "recommended_action": ""}
    if n <= 2:
        return {
            "severity": "warning",
            "suppress": False,
            "title": f"{n} {hw_word} behind",
            "body": (
                f"This student is currently {n} {hw_word} behind — "
                f"minor academic debt that is still easily recoverable."
            ),
            "recommended_action": (
                "Note at the next touchpoint. Ask if the student needs "
                "resources or a deadline extension for the overdue work."
            ),
        }
    if n <= 4:
        return {
            "severity": "elevated",
            "suppress": False,
            "title": f"{n} assignments behind",
            "body": (
                f"This student is {n} assignments behind. Academic debt is "
                f"building and may affect their ability to follow upcoming content."
            ),
            "recommended_action": (
                "Reach out this week. Help the student prioritise the most "
                "important overdue assignments and identify what is blocking "
                "completion."
            ),
        }
    # Critical: ≥5
    return {
        "severity": "critical",
        "suppress": False,
        "title": f"{n} assignments behind — academic debt is severe",
        "body": (
            f"This student is {n} assignments behind. This level of academic "
            f"debt is strongly correlated with program withdrawal if not "
            f"addressed immediately."
        ),
        "recommended_action": (
            "Escalate to academic advisor. The student needs a structured "
            "recovery plan — consider whether a timeline adjustment, incomplete "
            "grade, or formal support plan is appropriate."
        ),
    }


def _interp_avg_hw_score(v: float) -> Dict[str, Any]:
    score = f"{v:.0f}"
    # ≥85 → healthy; 70–84 → warning; 55–69 → elevated; <55 → critical
    if v >= 85:
        return {"severity": "healthy", "suppress": True,
                "title": "", "body": "", "recommended_action": ""}
    if v >= 70:
        return {
            "severity": "warning",
            "suppress": False,
            "title": f"Average assignment score is {score}",
            "body": (
                f"Average assignment score of {score} — passing but below the "
                f"85 benchmark. Some content gaps are likely present."
            ),
            "recommended_action": (
                "Review with the student at the next touchpoint. Ask which "
                "topics feel weakest and offer practice resources."
            ),
        }
    if v >= 55:
        return {
            "severity": "elevated",
            "suppress": False,
            "title": f"Low average assignment score — {score}",
            "body": (
                f"Average assignment score of {score}. This student is "
                f"struggling to demonstrate mastery of core content."
            ),
            "recommended_action": (
                "Schedule a targeted academic support session. Identify the "
                "2–3 topics causing the most difficulty and connect the student "
                "to appropriate resources."
            ),
        }
    # Critical: <55
    return {
        "severity": "critical",
        "suppress": False,
        "title": f"Average assignment score below passing — {score}",
        "body": (
            f"Average assignment score of {score} — below the passing "
            f"threshold. The student needs immediate academic support."
        ),
        "recommended_action": (
            "Immediate academic intervention. Determine whether tutoring, "
            "content re-review, or timeline adjustment is required. Do not "
            "wait for the next scheduled touchpoint."
        ),
    }


def _interp_submission_rate(v: float) -> Dict[str, Any]:
    pct = f"{v * 100:.0f}%"
    # ≥90% → healthy; 75–89% → warning; 50–74% → elevated; <50% → critical
    if v >= 0.90:
        return {"severity": "healthy", "suppress": True,
                "title": "", "body": "", "recommended_action": ""}
    if v >= 0.75:
        return {
            "severity": "warning",
            "suppress": False,
            "title": f"Assignment submission rate is {pct}",
            "body": (
                f"Submission rate of {pct} — some assignments are being "
                f"skipped. Worth confirming the student is keeping up."
            ),
            "recommended_action": (
                "Mention at the next touchpoint. Confirm there are no barriers "
                "to completing specific assignment types."
            ),
        }
    if v >= 0.50:
        return {
            "severity": "elevated",
            "suppress": False,
            "title": f"Low assignment submission rate — {pct}",
            "body": (
                f"Submission rate is {pct}. The student is missing a "
                f"significant portion of assigned work."
            ),
            "recommended_action": (
                "Contact this week. Understand which assignments are being "
                "skipped and why. Determine if workload, comprehension, or "
                "access barriers are the cause."
            ),
        }
    # Critical: <50%
    return {
        "severity": "critical",
        "suppress": False,
        "title": f"Critical submission rate — only {pct} of assignments submitted",
        "body": (
            f"Submission rate is {pct}. The student is not completing most "
            f"assigned work — a strong predictor of withdrawal."
        ),
        "recommended_action": (
            "Urgent outreach required. The student needs a clear, concrete "
            "action plan to re-engage with coursework before the gap widens "
            "further."
        ),
    }


def _interp_completion_rate(
    v: float,
    label: str,
    healthy_threshold: float,
    warning_threshold: float,
    elevated_threshold: float,
) -> Dict[str, Any]:
    pct = f"{v * 100:.0f}%"
    if v >= healthy_threshold:
        return {"severity": "healthy", "suppress": True,
                "title": "", "body": "", "recommended_action": ""}
    if v >= warning_threshold:
        return {
            "severity": "warning",
            "suppress": False,
            "title": f"Low {label} response rate — {pct}",
            "body": (
                f"This student has responded to {pct} of {label} attempts. "
                f"Inconsistent responsiveness — some messages are not getting "
                f"through."
            ),
            "recommended_action": (
                f"Review recent {label} delivery logs. Check whether messages "
                f"were received and whether timing or channel could be improved."
            ),
        }
    if v >= elevated_threshold:
        return {
            "severity": "elevated",
            "suppress": False,
            "title": f"Student responding to only {pct} of {label} attempts",
            "body": (
                f"This student has responded to only {pct} of {label} attempts. "
                f"The current approach is not reliably reaching this student."
            ),
            "recommended_action": (
                f"Change the {label} channel or timing. If email has been used, "
                f"try phone. If automated, try personal. Document what has been "
                f"tried."
            ),
        }
    # Critical: below elevated threshold
    return {
        "severity": "critical",
        "suppress": False,
        "title": f"{label.capitalize()} outreach has failed — {pct} response rate",
        "body": (
            f"This student has responded to only {pct} of {label} attempts. "
            f"Standard {label} messaging has not been effective."
        ),
        "recommended_action": (
            f"Escalate to direct personal phone or video contact. Automated "
            f"and standard {label} outreach has failed. Document all attempts "
            f"and outcomes."
        ),
    }


def _fallback_kpi(kpi_name: str, value: Any) -> Dict[str, Any]:
    """Preserve the pre-interpretation generic behaviour for unmapped KPIs."""
    return {
        "severity": "unknown",
        "suppress": False,
        "title": None,   # signals caller to use the old label-based title
        "body": None,    # signals caller to use the old confidence-based body
        "recommended_action": None,
    }


# ---------------------------------------------------------------------------
# Human-readable label maps for fingerprint patterns
# ---------------------------------------------------------------------------

_PATTERN_TITLE: Dict[str, str] = {
    "active_but_disconnected": "Enrolled but not engaging with the platform",
    "low_trigger_completion":  "Low student response to advisor outreach",
    "stale_login_pattern":     "No login activity for an extended period",
    "stale_activity_pattern":  "No platform activity for an extended period",
    "rapid_disengagement":     "Sharp recent decline in engagement",
    "chronic_inactivity":      "No meaningful platform engagement recorded",
}

_PATTERN_BODY: Dict[str, str] = {
    "active_but_disconnected": (
        "This student is currently enrolled and marked active, "
        "but recent platform engagement is extremely low."
    ),
    "low_trigger_completion": (
        "This student has been included in multiple advisor outreach or intervention workflows, "
        "but few of those attempts appear to have reached completion."
    ),
    "stale_login_pattern": (
        "No login activity has been recorded for this student for an extended period. "
        "This may indicate lost access, reduced motivation, or a scheduling disruption."
    ),
    "stale_activity_pattern": (
        "No meaningful platform activity has been detected for this student for an extended period. "
        "This pattern is often an early indicator of disengagement."
    ),
    "rapid_disengagement": (
        "Recent engagement activity has declined sharply over a short period of time. "
        "This student may be experiencing a disruption that warrants prompt attention."
    ),
    "chronic_inactivity": (
        "No meaningful platform engagement has been recorded for an extended period. "
        "Advisor outreach is strongly recommended before the gap widens further."
    ),
}

# Human-readable labels for KPI names shown in card titles
_KPI_LABEL: Dict[str, str] = {
    "last_activity_days":           "Days since last platform activity",
    "last_login_days":              "Days since last login",
    "attendance_percentage":        "Attendance rate",
    "homeworks_behind":             "Assignments behind",
    "avg_hw_score":                 "Average assignment score",
    "trigger_completion_rate":      "Outreach response rate",
    "total_triggers_fired":         "Total outreach attempts",
    "submission_rate":              "Assignment submission rate",
}


class InsightGenerator:

    def _enrich_with_explanation(
        self, insight: Insight, pattern_name: str = ""
    ) -> Insight:
        """Pass the insight through the explainer skill and attach the result."""
        result = generate_explanation({
            "title":        insight.title,
            "confidence":   insight.confidence,
            "entity_type":  insight.entity_type,
            "pattern_name": pattern_name,
        })
        insight.explanation = result["explanation"]
        insight.recommended_action = result["recommended_action"]
        return insight

    def generate_insights(
        self,
        kpis: List[Dict[str, Any]],
        fingerprints: List[Dict[str, Any]],
        entity_id: str,
        entity_type: str,
    ) -> InsightGenerationResult:

        insights: List[Insight] = []

        for kpi in kpis:
            if kpi.get("confidence", 0.0) > 0.7:
                raw_name   = kpi.get("kpi_name", "unknown")
                kpi_value  = kpi.get("value")
                kpi_unit   = kpi.get("unit", "")
                confidence = kpi.get("confidence", 0.0)

                interp = interpret_kpi(raw_name, kpi_value, kpi_unit)

                # Healthy signals are suppressed — no insight needed.
                if interp["suppress"]:
                    continue

                # Mapped KPI: use interpretation-driven title and body.
                if interp["title"] is not None:
                    title = interp["title"]
                    body  = interp["body"]
                else:
                    # Unmapped KPI: preserve original generic label behaviour.
                    label = _KPI_LABEL.get(raw_name, raw_name.replace("_", " ").capitalize())
                    title = f"Engagement signal: {label}"
                    body  = (
                        f"'{label}' is a high-confidence engagement indicator "
                        f"for this student (confidence: {confidence:.0%})."
                    )

                insight = Insight(
                    title=title,
                    body=body,
                    insight_type="kpi",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    source_kpis={raw_name: confidence},
                    source_patterns={},
                    confidence=confidence,
                )

                # For mapped KPIs attach the deterministic recommended_action
                # directly; skip the generic explainer for those fields.
                if interp["title"] is not None and interp["recommended_action"]:
                    insight.recommended_action = interp["recommended_action"]
                    # explanation still uses the generic explainer path.
                    insight = self._enrich_with_explanation(insight)
                    # Override recommended_action with the deterministic version.
                    insight.recommended_action = interp["recommended_action"]
                else:
                    insight = self._enrich_with_explanation(insight)

                insights.append(insight)

        for fp in fingerprints:
            if fp.get("risk_level") == "high":
                raw_pattern = fp.get("pattern_name", "unknown")
                title = _PATTERN_TITLE.get(
                    raw_pattern,
                    raw_pattern.replace("_", " ").capitalize(),
                )
                body = _PATTERN_BODY.get(
                    raw_pattern,
                    f"A concern has been identified for this student: {raw_pattern.replace('_', ' ')}.",
                )
                insights.append(
                    self._enrich_with_explanation(
                        Insight(
                            title=title,
                            body=body,
                            insight_type="risk",
                            entity_type=fp.get("entity_type", ""),
                            entity_id=fp.get("entity_id", 0),
                            source_kpis={},
                            source_patterns={raw_pattern: fp.get("score", 0.0)},
                            confidence=fp.get("score", 0.0),
                        ),
                        pattern_name=raw_pattern,
                    )
                )

        return InsightGenerationResult(
            insights=insights,
            generated_count=len(insights),
            analyzed_kpis=len(kpis),
            analyzed_fingerprints=len(fingerprints),
        )
