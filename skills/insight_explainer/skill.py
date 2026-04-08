"""
Skill: insight_explainer

Converts a raw insight dict into a human-readable explanation and a
recommended action. Pure logic — no I/O, no external dependencies.
"""


def _confidence_label(confidence: float) -> str:
    """Map a 0–1 confidence score to a plain-language phrase."""
    if confidence >= 0.90:
        return "high confidence"
    if confidence >= 0.75:
        return "fairly confident"
    if confidence >= 0.50:
        return "moderate confidence"
    return "an uncertain signal"


def _entity_phrase(entity_type: str) -> str:
    """Return a natural noun phrase for the entity type."""
    mapping = {
        "student": "this student",
        "cohort": "this cohort",
        "mentor": "this mentor",
        "instructor": "this instructor",
    }
    return mapping.get(entity_type.lower(), f"this {entity_type.lower()}")


def _build_explanation(title: str, confidence: float, entity_type: str) -> str:
    entity = _entity_phrase(entity_type)
    confidence_phrase = _confidence_label(confidence)
    return (
        f"The system has detected a pattern described as '{title}' for {entity}. "
        f"This is an {confidence_phrase} signal, meaning the underlying data "
        f"strongly supports this finding and it is worth reviewing."
        if confidence >= 0.75
        else
        f"The system has detected a possible pattern described as '{title}' for {entity}. "
        f"This is {confidence_phrase} — the data suggests something may be worth "
        f"looking into, but it should be interpreted with care."
    )


def _build_recommended_action(title: str, entity_type: str) -> str:
    entity = _entity_phrase(entity_type)
    title_lower = title.lower()

    if "quiz" in title_lower or "score" in title_lower or "assessment" in title_lower:
        return (
            f"Schedule a check-in with {entity} to identify which topics they are "
            f"finding difficult and offer targeted review resources or additional practice."
        )
    if "engagement" in title_lower or "participation" in title_lower or "attendance" in title_lower:
        return (
            f"Reach out to {entity} to understand any barriers to participation "
            f"and explore ways to re-engage them with the program."
        )
    if "progress" in title_lower or "milestone" in title_lower or "completion" in title_lower:
        return (
            f"Review the current progress plan for {entity} and adjust pacing, "
            f"deadlines, or support resources as needed."
        )
    if "risk" in title_lower or "dropout" in title_lower or "churn" in title_lower:
        return (
            f"Prioritize a personal outreach to {entity} and connect them with "
            f"an advisor or mentor who can provide direct support."
        )

    # Generic fallback
    return (
        f"Review the available data for {entity} and discuss this finding with "
        f"the relevant advisor or team member to determine the best next step."
    )


def generate_explanation(insight: dict) -> dict:
    """
    Convert a raw insight into a human-readable explanation and recommended action.

    Args:
        insight: dict with keys:
            - title (str): Short label for the insight.
            - confidence (float): Model certainty, between 0.0 and 1.0.
            - entity_type (str): Who the insight is about (e.g. "student").

    Returns:
        dict with keys:
            - explanation (str): Plain-language description of what the insight means.
            - recommended_action (str): Concrete next step for a human to take.

    Raises:
        ValueError: If any required field is missing or invalid.
    """
    title = insight.get("title")
    confidence = insight.get("confidence")
    entity_type = insight.get("entity_type")

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
        "explanation": _build_explanation(title, confidence, entity_type),
        "recommended_action": _build_recommended_action(title, entity_type),
    }
