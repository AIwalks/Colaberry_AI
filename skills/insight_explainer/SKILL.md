# Skill: insight_explainer

## Purpose

Converts raw insight data (title, confidence score, entity type) into a human-readable explanation and a clear, actionable recommendation.

This skill is designed for non-technical audiences — coaches, advisors, and students — who need to understand what an insight means and what to do about it.

---

## Inputs

A single `dict` with the following fields:

| Field         | Type    | Required | Description                                         |
|---------------|---------|----------|-----------------------------------------------------|
| `title`       | str     | Yes      | The short label of the insight (e.g. "Low Quiz Score") |
| `confidence`  | float   | Yes      | A value between 0.0 and 1.0 representing model certainty |
| `entity_type` | str     | Yes      | Who or what the insight is about (e.g. "student", "cohort", "mentor") |

**Example input:**
```json
{
  "title": "Low Quiz Score",
  "confidence": 0.85,
  "entity_type": "student"
}
```

---

## Outputs

A single `dict` with the following fields:

| Field                | Type | Description                                              |
|----------------------|------|----------------------------------------------------------|
| `explanation`        | str  | A plain-language sentence describing what the insight means |
| `recommended_action` | str  | A concrete, actionable next step for a human to take     |

**Example output:**
```json
{
  "explanation": "This student is showing signs of difficulty with recent quiz material. The system is fairly confident this pattern is real and worth attention.",
  "recommended_action": "Schedule a check-in with this student to identify which topics they are struggling with and offer targeted review resources."
}
```

---

## Rules

1. **No jargon** — confidence scores must be translated into plain language (e.g. "fairly confident", "highly confident").
2. **No database calls** — this skill operates on data passed in directly.
3. **No API calls** — pure logic only; no external dependencies.
4. **Always return both fields** — `explanation` and `recommended_action` must always be present.
5. **Tone must be constructive** — explanations should be supportive, not alarming.
6. **Entity-aware language** — the explanation must reference the correct entity type naturally (e.g. "this student", "this cohort").
7. **Confidence bands** — use the following thresholds for plain-language translation:
   - `< 0.5` → "uncertain signal"
   - `0.5 – 0.74` → "moderate confidence"
   - `0.75 – 0.89` → "fairly confident"
   - `>= 0.9` → "high confidence"
