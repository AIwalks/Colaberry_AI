"""
Skill: insight_explainer

Converts a raw insight dict into a human-readable explanation and a
recommended action. Pure logic — no I/O, no external dependencies.
"""

# ---------------------------------------------------------------------------
# Pattern-specific narrative maps
# These fire before the generic keyword fallbacks.
# Keys match the raw pattern_name values written by FingerprintGeneratorService.
# ---------------------------------------------------------------------------

_PATTERN_EXPLANATION = {
    "active_but_disconnected": (
        "This student is currently enrolled and marked active, but their recent platform "
        "engagement is extremely low. The gap between enrollment status and actual activity "
        "suggests the student may be present on paper but not participating in practice."
    ),
    "low_trigger_completion": (
        "This student has been repeatedly included in advisor outreach or intervention "
        "workflows, but few of those attempts appear to have reached completion. This may "
        "indicate the student is not receiving messages, is not responding, or is experiencing "
        "a barrier that outreach has not yet addressed."
    ),
    "stale_login_pattern": (
        "No login activity has been recorded for this student for an extended period. "
        "This may indicate the student has lost platform access, lost motivation, or has "
        "stopped engaging with coursework. A direct check-in is warranted."
    ),
    "stale_activity_pattern": (
        "No meaningful platform activity has been detected for this student for an extended "
        "period. This pattern frequently precedes disengagement or withdrawal and should be "
        "reviewed before the gap widens further."
    ),
    "rapid_disengagement": (
        "This student's engagement activity has declined sharply over a short period. "
        "A sudden drop of this kind often corresponds to a life disruption, technical issue, "
        "or motivation barrier that can be resolved if addressed promptly."
    ),
    "chronic_inactivity": (
        "This student has shown no meaningful platform engagement for an extended period. "
        "Without intervention, this level of inactivity substantially increases the risk "
        "of the student falling behind or withdrawing from the program."
    ),
}

_PATTERN_ACTION = {
    "active_but_disconnected": (
        "Have an advisor contact this student directly this week to confirm platform access, "
        "verify their current schedule status, and understand any barriers preventing "
        "participation. Log the contact attempt and outcome."
    ),
    "low_trigger_completion": (
        "Review which outreach workflows this student was included in and determine whether "
        "they were delivered successfully. If delivery was confirmed, escalate to a personal "
        "phone or video call to understand why the student has not been responding."
    ),
    "stale_login_pattern": (
        "Contact this student directly — by phone if email has gone unanswered — to confirm "
        "they can still access the platform and to identify any technical or motivational "
        "barriers. Verify their login credentials have not expired."
    ),
    "stale_activity_pattern": (
        "Assign an advisor to reach out to this student this week. Confirm their current "
        "participation status, check whether they have completed recent assignments, and "
        "determine whether a schedule adjustment or additional support is needed."
    ),
    "rapid_disengagement": (
        "Prioritize an immediate personal outreach to this student. Ask specifically about "
        "recent changes in their schedule, workload, or circumstances. Offer a brief check-in "
        "call and document the outcome so the team can track whether engagement recovers."
    ),
    "chronic_inactivity": (
        "Escalate this student to the advisor team for a direct personal outreach this week. "
        "The goal is to confirm whether the student is still enrolled, identify what is "
        "preventing engagement, and determine whether a formal intervention plan is needed."
    ),
}


# ---------------------------------------------------------------------------
# Generic helpers (used when no pattern-specific match is found)
# ---------------------------------------------------------------------------

def _confidence_label(confidence: float) -> str:
    if confidence >= 0.90:
        return "high confidence"
    if confidence >= 0.75:
        return "fairly confident"
    if confidence >= 0.50:
        return "moderate confidence"
    return "a low-confidence"


def _entity_phrase(entity_type: str) -> str:
    mapping = {
        "student":    "this student",
        "cohort":     "this cohort",
        "mentor":     "this mentor",
        "instructor": "this instructor",
    }
    return mapping.get(entity_type.lower(), f"this {entity_type.lower()}")


def _build_explanation(
    title: str, confidence: float, entity_type: str, pattern_name: str = ""
) -> str:
    # Pattern-specific narrative takes priority
    if pattern_name and pattern_name in _PATTERN_EXPLANATION:
        return _PATTERN_EXPLANATION[pattern_name]

    entity = _entity_phrase(entity_type)
    confidence_phrase = _confidence_label(confidence)
    if confidence >= 0.75:
        return (
            f"A {confidence_phrase} concern has been identified for {entity}: {title}. "
            f"The available data strongly supports this finding and it warrants review."
        )
    return (
        f"A {confidence_phrase} signal has been detected for {entity}: {title}. "
        f"The data suggests something may be worth looking into, "
        f"but should be interpreted alongside other available context."
    )


def _build_recommended_action(
    title: str, entity_type: str, pattern_name: str = ""
) -> str:
    # Pattern-specific action takes priority
    if pattern_name and pattern_name in _PATTERN_ACTION:
        return _PATTERN_ACTION[pattern_name]

    entity = _entity_phrase(entity_type)
    title_lower = title.lower()

    if "quiz" in title_lower or "score" in title_lower or "assessment" in title_lower:
        return (
            f"Schedule a check-in with {entity} to identify which topics they are "
            f"finding difficult and offer targeted review resources or additional practice."
        )
    if "attendance" in title_lower:
        return (
            f"Contact {entity} to understand any barriers to attendance "
            f"and explore scheduling or participation options."
        )
    if "engagement" in title_lower or "participation" in title_lower or "activity" in title_lower:
        return (
            f"Have an advisor reach out to {entity} directly this week to understand "
            f"what is preventing engagement and identify what support is needed."
        )
    if "outreach" in title_lower or "response" in title_lower:
        return (
            f"Review recent outreach history for {entity} and follow up with a direct "
            f"phone or video call if previous messages have gone unanswered."
        )
    if "login" in title_lower or "access" in title_lower:
        return (
            f"Confirm that {entity} can still access the platform and verify their "
            f"login credentials have not expired."
        )

    return (
        f"Have an advisor review the available data for {entity} and follow up directly "
        f"to determine whether additional support or outreach is needed this week."
    )


def generate_explanation(insight: dict) -> dict:
    """
    Convert a raw insight into a human-readable explanation and recommended action.

    Args:
        insight: dict with keys:
            - title (str): Short label for the insight.
            - confidence (float): Model certainty, between 0.0 and 1.0.
            - entity_type (str): Who the insight is about (e.g. "student").
            - pattern_name (str, optional): Internal pattern identifier for
              pattern-specific narrative lookup.

    Returns:
        dict with keys:
            - explanation (str): Plain-language description of what the insight means.
            - recommended_action (str): Concrete next step for a human to take.

    Raises:
        ValueError: If any required field is missing or invalid.
    """
    title        = insight.get("title")
    confidence   = insight.get("confidence")
    entity_type  = insight.get("entity_type")
    pattern_name = insight.get("pattern_name", "")

    if not title or not isinstance(title, str):
        raise ValueError("insight must include a non-empty string 'title'")
    if confidence is None or not isinstance(confidence, (int, float)):
        raise ValueError("insight must include a numeric 'confidence' between 0.0 and 1.0")
    if not (0.0 <= float(confidence) <= 1.0):
        raise ValueError("'confidence' must be between 0.0 and 1.0")
    if not entity_type or not isinstance(entity_type, str):
        raise ValueError("insight must include a non-empty string 'entity_type'")

    confidence = float(confidence)

    return {
        "explanation":        _build_explanation(title, confidence, entity_type, pattern_name),
        "recommended_action": _build_recommended_action(title, entity_type, pattern_name),
    }
