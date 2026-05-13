"""Unit tests for services/ai_insight_service.py.

All tests are isolated and deterministic — no real Claude API calls are made.
The seam under test is generate_ai_insight(); _call_claude() is mocked
to control every failure path without network access.
"""

import json
import sys
from unittest.mock import patch

from services.ai_insight_service import _FALLBACK, generate_ai_insight

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_STUDENT_DATA = {
    "entity_id": "student_101",
    "entity_type": "student",
    "kpis": [
        {
            "kpi_name": "avg_logins_per_week",
            "source_pattern": "disengagement",
            "confidence": 0.92,
            "sample_size": 120,
        },
        {
            "kpi_name": "session_duration_drop",
            "source_pattern": "dropout_risk",
            "confidence": 0.81,
            "sample_size": 85,
        },
    ],
    "fingerprints": [
        {
            "pattern_name": "disengagement",
            "risk_level": "high",
            "score": 1.0,
        }
    ],
}

_VALID_CLAUDE_RESPONSE = {
    "summary": "Student 101 shows strong disengagement signals across login frequency and session duration.",
    "risk_level": "high",
    "confidence": 0.89,
    "recommended_action": "Schedule a 1:1 check-in within 48 hours and review homework submission backlog.",
    "explainability": [
        "Login frequency KPI has 92% confidence disengagement pattern across 120 students.",
        "Session duration drop KPI indicates active avoidance behaviour (81% confidence).",
        "Behavioral fingerprint score is 1.0 — all disengagement thresholds matched.",
    ],
}


# ---------------------------------------------------------------------------
# Test 1 — missing ANTHROPIC_API_KEY returns fallback immediately
# ---------------------------------------------------------------------------

def test_missing_api_key_returns_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = generate_ai_insight(_STUDENT_DATA)

    assert result == _FALLBACK
    assert result["confidence"] == 0.0
    assert result["risk_level"] == "unknown"


def test_missing_api_key_does_not_call_claude(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with patch("services.ai_insight_service._call_claude") as mock_call:
        generate_ai_insight(_STUDENT_DATA)

    mock_call.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — anthropic package not installed raises ImportError → fallback
# ---------------------------------------------------------------------------

def test_import_error_returns_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    # Setting sys.modules["anthropic"] = None causes Python to raise
    # ImportError on the next `import anthropic` statement.
    with patch.dict(sys.modules, {"anthropic": None}):
        result = generate_ai_insight(_STUDENT_DATA)

    assert result == _FALLBACK
    assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Test 3 — Claude returns invalid JSON → fallback
# ---------------------------------------------------------------------------

def test_invalid_json_response_returns_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    with patch("services.ai_insight_service._call_claude") as mock_call:
        mock_call.side_effect = json.JSONDecodeError("Expecting value", "not json", 0)
        result = generate_ai_insight(_STUDENT_DATA)

    assert result == _FALLBACK
    assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Test 4 — successful valid response returns structured output
# ---------------------------------------------------------------------------

def test_valid_response_returns_structured_output(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    with patch("services.ai_insight_service._call_claude") as mock_call:
        mock_call.return_value = _VALID_CLAUDE_RESPONSE.copy()
        result = generate_ai_insight(_STUDENT_DATA)

    assert result["risk_level"] == "high"
    assert result["confidence"] == 0.89
    assert isinstance(result["summary"], str) and len(result["summary"]) > 0
    assert isinstance(result["recommended_action"], str) and len(result["recommended_action"]) > 0
    assert isinstance(result["explainability"], list)
    assert len(result["explainability"]) >= 2


def test_valid_response_calls_claude_exactly_once(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    with patch("services.ai_insight_service._call_claude") as mock_call:
        mock_call.return_value = _VALID_CLAUDE_RESPONSE.copy()
        generate_ai_insight(_STUDENT_DATA)

    mock_call.assert_called_once()


def test_valid_response_confidence_is_float(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    # Claude may return confidence as a string — _validate must coerce it.
    response = _VALID_CLAUDE_RESPONSE.copy()
    response["confidence"] = "0.89"

    with patch("services.ai_insight_service._call_claude") as mock_call:
        mock_call.return_value = response
        result = generate_ai_insight(_STUDENT_DATA)

    assert isinstance(result["confidence"], float)
    assert result["confidence"] == 0.89


# ---------------------------------------------------------------------------
# Test 5 — validation failures return fallback
# ---------------------------------------------------------------------------

def test_missing_required_field_returns_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    incomplete = {
        "summary": "Partial response",
        "risk_level": "high",
        # missing: confidence, recommended_action, explainability
    }

    with patch("services.ai_insight_service._call_claude") as mock_call:
        mock_call.return_value = incomplete
        result = generate_ai_insight(_STUDENT_DATA)

    assert result == _FALLBACK


def test_invalid_risk_level_returns_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    bad_risk = _VALID_CLAUDE_RESPONSE.copy()
    bad_risk["risk_level"] = "extreme"  # not in {low, medium, high, critical}

    with patch("services.ai_insight_service._call_claude") as mock_call:
        mock_call.return_value = bad_risk
        result = generate_ai_insight(_STUDENT_DATA)

    assert result == _FALLBACK


def test_explainability_not_a_list_returns_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    bad_explainability = _VALID_CLAUDE_RESPONSE.copy()
    bad_explainability["explainability"] = "should be a list, not a string"

    with patch("services.ai_insight_service._call_claude") as mock_call:
        mock_call.return_value = bad_explainability
        result = generate_ai_insight(_STUDENT_DATA)

    assert result == _FALLBACK


# ---------------------------------------------------------------------------
# Test 6 — unexpected API exception returns fallback (network, rate limit, etc.)
# ---------------------------------------------------------------------------

def test_generic_api_exception_returns_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    with patch("services.ai_insight_service._call_claude") as mock_call:
        mock_call.side_effect = Exception("connection timeout")
        result = generate_ai_insight(_STUDENT_DATA)

    assert result == _FALLBACK
    assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Test 7 — fallback shape contract is always satisfied
# ---------------------------------------------------------------------------

def test_fallback_has_required_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = generate_ai_insight(_STUDENT_DATA)

    required_keys = {"summary", "risk_level", "confidence", "recommended_action", "explainability"}
    assert required_keys.issubset(result.keys())


def test_fallback_is_independent_copy(monkeypatch):
    # Mutating one fallback result must not affect subsequent calls.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result_a = generate_ai_insight(_STUDENT_DATA)
    result_a["risk_level"] = "mutated"

    result_b = generate_ai_insight(_STUDENT_DATA)

    assert result_b["risk_level"] == "unknown"
