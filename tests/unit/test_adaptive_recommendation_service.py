"""Unit tests for services/adaptive_recommendation_service.py.

All tests use mock DB sessions — no live DB or MSSQL required.
random.random and random.choice are patched to make epsilon-greedy behavior
deterministic.

Coverage
────────
- Pool found: select_key returns a key from the pool candidates
- Missing pool: returns fallback_key without touching learning service
- Inactive pool: query returns None (is_active filter excludes it); fallback returned
- Empty candidate list: returns fallback_key + WARNING log
- Malformed candidate JSON: returns fallback_key + WARNING log
- None candidate JSON: falls back via the 'or "[]"' guard; returns fallback_key
- Exploitation path (draw >= epsilon): returns ranked[0]
- Exploitation at epsilon boundary (draw == epsilon): exploitation fires (not <)
- Exploration path (draw < epsilon): random.choice called on full candidates
- Exploration uses full candidate list, not the ranked subset
- epsilon_override replaces system default 0.05
- Default epsilon 0.05 used when epsilon_override is None
- min_sample_override passed to get_ranked_keys
- Default min_sample 10 used when min_sample_override is None
- dimension and risk_level forwarded to get_ranked_keys
- candidates passed positionally to get_ranked_keys
- Learning service fallback (ranked == candidates): ranked[0] is candidates[0]
- DB query exception: returns fallback_key + WARNING log; does not raise
- Learning service exception: returns fallback_key; does not raise
- Return value is always str on happy path
- Return value is always str on error path
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.adaptive_recommendation_service import AdaptiveRecommendationService


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_TRIGGER    = "reach_out"
_DIMENSION  = "attendance"
_RISK       = "high"
_FALLBACK   = "reach_out_high"
_CANDIDATES = ["key_a", "key_b", "key_c"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc() -> AdaptiveRecommendationService:
    return AdaptiveRecommendationService()


def _make_db(pool_result=None) -> MagicMock:
    """Mock session whose query chain returns pool_result from .first()."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = pool_result
    return db


def _make_pool(
    candidate_keys_json: str | None = '["key_a", "key_b", "key_c"]',
    epsilon_override: float | None = None,
    min_sample_override: int | None = None,
) -> MagicMock:
    """Mock RecommendationCandidatePool row with the given attributes."""
    pool = MagicMock()
    pool.candidate_keys_json = candidate_keys_json
    pool.epsilon_override    = epsilon_override
    pool.min_sample_override = min_sample_override
    pool.is_active           = True
    return pool


def _patch_learning(ranked=None):
    """Patch RecommendationLearningService.get_ranked_keys to return `ranked`."""
    if ranked is None:
        ranked = _CANDIDATES
    mock_cls = patch(
        "services.adaptive_recommendation_service.RecommendationLearningService"
    )
    return mock_cls, ranked


# ---------------------------------------------------------------------------
# TestPoolLookup
# ---------------------------------------------------------------------------

class TestPoolLookup:

    def test_pool_found_returns_key_from_candidates(self):
        pool = _make_pool()
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result in _CANDIDATES

    def test_missing_pool_returns_fallback_key(self):
        db = _make_db(pool_result=None)

        result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result == _FALLBACK

    def test_missing_pool_does_not_call_learning_service(self):
        db = _make_db(pool_result=None)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc:
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_svc.return_value.get_ranked_keys.assert_not_called()

    def test_inactive_pool_treated_as_missing(self):
        # The is_active==True filter causes the query to return None for
        # inactive rows — modelled by pool_result=None.
        db = _make_db(pool_result=None)

        result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result == _FALLBACK


# ---------------------------------------------------------------------------
# TestCandidateParsing
# ---------------------------------------------------------------------------

class TestCandidateParsing:

    def test_empty_candidate_list_returns_fallback_key(self):
        pool = _make_pool(candidate_keys_json="[]")
        db   = _make_db(pool)

        result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result == _FALLBACK

    def test_empty_candidate_list_logs_warning(self):
        pool = _make_pool(candidate_keys_json="[]")
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.logger") as mock_log:
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_log.warning.assert_called()

    def test_malformed_json_returns_fallback_key(self):
        pool = _make_pool(candidate_keys_json="not valid json {[}")
        db   = _make_db(pool)

        result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result == _FALLBACK

    def test_malformed_json_logs_warning(self):
        pool = _make_pool(candidate_keys_json="{bad}")
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.logger") as mock_log:
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_log.warning.assert_called()

    def test_none_candidate_json_returns_fallback_key(self):
        # candidate_keys_json=None — the 'or "[]"' guard in json.loads prevents
        # a TypeError and falls through to the empty-list check.
        pool = _make_pool(candidate_keys_json=None)
        db   = _make_db(pool)

        result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result == _FALLBACK


# ---------------------------------------------------------------------------
# TestEpsilonGreedyExploitation
# ---------------------------------------------------------------------------

class TestEpsilonGreedyExploitation:

    def test_exploitation_returns_ranked_first(self):
        """draw >= epsilon → ranked[0] returned, not a random choice."""
        pool   = _make_pool()
        db     = _make_db(pool)
        ranked = ["key_b", "key_a", "key_c"]

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.return_value = ranked
            result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result == "key_b"

    def test_exploitation_does_not_call_random_choice(self):
        """Exploitation path must not call random.choice."""
        pool = _make_pool()
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99), \
             patch("services.adaptive_recommendation_service.random.choice") as mock_choice:
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_choice.assert_not_called()

    def test_exploitation_at_epsilon_boundary_exploits(self):
        """draw exactly equal to epsilon (0.05 < 0.05 is False) → exploitation."""
        pool   = _make_pool(epsilon_override=0.05)
        db     = _make_db(pool)
        ranked = ["key_a", "key_b"]

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.05), \
             patch("services.adaptive_recommendation_service.random.choice") as mock_choice:
            mock_svc.return_value.get_ranked_keys.return_value = ranked
            result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_choice.assert_not_called()
        assert result == "key_a"


# ---------------------------------------------------------------------------
# TestEpsilonGreedyExploration
# ---------------------------------------------------------------------------

class TestEpsilonGreedyExploration:

    def test_exploration_calls_random_choice(self):
        """draw < epsilon → random.choice invoked."""
        pool = _make_pool()
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.00), \
             patch("services.adaptive_recommendation_service.random.choice", return_value="key_c") as mock_choice:
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_choice.assert_called_once_with(_CANDIDATES)
        assert result == "key_c"

    def test_exploration_uses_full_candidate_list_not_ranked(self):
        """Exploration must sample from the full pool, not the ranked subset,
        so that candidates with no history still get explored.
        """
        pool   = _make_pool()
        db     = _make_db(pool)
        ranked = ["key_a", "key_b"]  # key_c absent from ranked (insufficient sample)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.00), \
             patch("services.adaptive_recommendation_service.random.choice") as mock_choice:
            mock_svc.return_value.get_ranked_keys.return_value = ranked
            mock_choice.return_value = "key_c"
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        # Must receive ALL candidates, not just the ranked subset.
        mock_choice.assert_called_once_with(_CANDIDATES)


# ---------------------------------------------------------------------------
# TestAdaptiveParameters
# ---------------------------------------------------------------------------

class TestAdaptiveParameters:

    def test_default_epsilon_triggers_exploration_below_005(self):
        """epsilon_override=None → system default 0.05; draw=0.04 < 0.05 → exploration."""
        pool = _make_pool(epsilon_override=None)
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.04), \
             patch("services.adaptive_recommendation_service.random.choice") as mock_choice:
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            mock_choice.return_value = _CANDIDATES[0]
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_choice.assert_called_once()

    def test_default_epsilon_triggers_exploitation_at_005(self):
        """draw=0.05 is not < 0.05 → exploitation when epsilon is default."""
        pool = _make_pool(epsilon_override=None)
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.05), \
             patch("services.adaptive_recommendation_service.random.choice") as mock_choice:
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_choice.assert_not_called()

    def test_epsilon_override_raises_exploration_threshold(self):
        """epsilon_override=0.20; draw=0.10 < 0.20 → exploration fires."""
        pool = _make_pool(epsilon_override=0.20)
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.10), \
             patch("services.adaptive_recommendation_service.random.choice") as mock_choice:
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            mock_choice.return_value = _CANDIDATES[0]
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_choice.assert_called_once()

    def test_default_min_sample_10_passed_to_get_ranked_keys(self):
        """min_sample_override=None → 10 forwarded to get_ranked_keys."""
        pool = _make_pool(min_sample_override=None)
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        _, kwargs = mock_svc.return_value.get_ranked_keys.call_args
        assert kwargs["min_sample"] == 10

    def test_min_sample_override_passed_to_get_ranked_keys(self):
        """min_sample_override=5 → 5 forwarded to get_ranked_keys."""
        pool = _make_pool(min_sample_override=5)
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        _, kwargs = mock_svc.return_value.get_ranked_keys.call_args
        assert kwargs["min_sample"] == 5


# ---------------------------------------------------------------------------
# TestLearningServiceIntegration
# ---------------------------------------------------------------------------

class TestLearningServiceIntegration:

    def test_dimension_forwarded_to_get_ranked_keys(self):
        pool = _make_pool()
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        _, kwargs = mock_svc.return_value.get_ranked_keys.call_args
        assert kwargs["dimension"] == _DIMENSION

    def test_risk_level_forwarded_to_get_ranked_keys(self):
        pool = _make_pool()
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        _, kwargs = mock_svc.return_value.get_ranked_keys.call_args
        assert kwargs["risk_level"] == _RISK

    def test_candidates_forwarded_positionally_to_get_ranked_keys(self):
        pool = _make_pool()
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        pos_args, _ = mock_svc.return_value.get_ranked_keys.call_args
        # pos_args = (db, candidates); candidates is the second positional argument
        assert pos_args[1] == _CANDIDATES

    def test_learning_service_fallback_uses_first_pool_candidate(self):
        """get_ranked_keys() returns list(candidates) on its own exception.
        Exploitation must then use candidates[0] — a valid string from the pool.
        """
        pool = _make_pool()
        db   = _make_db(pool)
        # Simulate get_ranked_keys falling back to original unranked order
        fallback_ranked = list(_CANDIDATES)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.return_value = fallback_ranked
            result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result == _CANDIDATES[0]
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# TestDefensiveness
# ---------------------------------------------------------------------------

class TestDefensiveness:

    def test_db_query_exception_returns_fallback_key(self):
        db = MagicMock()
        db.query.side_effect = Exception("DB connection refused")

        result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result == _FALLBACK

    def test_db_query_exception_does_not_raise(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("unexpected db error")

        # Must not raise — defensive contract requires this
        result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert isinstance(result, str)

    def test_db_query_exception_logs_warning(self):
        db = MagicMock()
        db.query.side_effect = Exception("timeout")

        with patch("services.adaptive_recommendation_service.logger") as mock_log:
            _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        mock_log.warning.assert_called()

    def test_learning_service_exception_returns_fallback_key(self):
        pool = _make_pool()
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.side_effect = RuntimeError("svc error")
            result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert result == _FALLBACK

    def test_learning_service_exception_does_not_raise(self):
        pool = _make_pool()
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.side_effect = RuntimeError("svc error")
            result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert isinstance(result, str)

    def test_return_value_is_always_str_on_happy_path(self):
        pool = _make_pool()
        db   = _make_db(pool)

        with patch("services.adaptive_recommendation_service.RecommendationLearningService") as mock_svc, \
             patch("services.adaptive_recommendation_service.random.random", return_value=0.99):
            mock_svc.return_value.get_ranked_keys.return_value = _CANDIDATES
            result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert isinstance(result, str)

    def test_return_value_is_always_str_on_db_error(self):
        db = MagicMock()
        db.query.side_effect = Exception("any error")

        result = _svc().select_key(db, _TRIGGER, _DIMENSION, _RISK, _FALLBACK)

        assert isinstance(result, str)
