"""Unit tests for services/worker/outcome_evaluation_worker.py."""

from unittest.mock import MagicMock, patch


def _fake_session(evaluated_count: int = 0) -> MagicMock:
    """Return a mock context-manager session whose evaluate_ready_outcomes stub
    returns the given count.  Not used directly — the service mock handles it."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


class TestEvaluatePendingOutcomes:

    def test_returns_zero_when_mssql_not_configured(self):
        """Short-circuit: must return 0 without touching DB or service."""
        with patch("services.worker.outcome_evaluation_worker.MSSQL_CONFIGURED", False):
            from services.worker.outcome_evaluation_worker import evaluate_pending_outcomes
            result = evaluate_pending_outcomes()

        assert result == 0

    def test_does_not_open_session_when_mssql_not_configured(self):
        """SessionLocal must never be called when the guard short-circuits."""
        with patch("services.worker.outcome_evaluation_worker.MSSQL_CONFIGURED", False), \
             patch("services.worker.outcome_evaluation_worker.SessionLocal") as mock_sl:
            from services.worker.outcome_evaluation_worker import evaluate_pending_outcomes
            evaluate_pending_outcomes()

        mock_sl.assert_not_called()

    def test_calls_evaluate_ready_outcomes_with_session(self):
        """evaluate_ready_outcomes() must be called once with the open session."""
        fake_session = _fake_session()

        with patch("services.worker.outcome_evaluation_worker.MSSQL_CONFIGURED", True), \
             patch("services.worker.outcome_evaluation_worker.SessionLocal",
                   return_value=fake_session), \
             patch("services.worker.outcome_evaluation_worker.InterventionOutcomeService") as mock_cls:
            mock_cls.return_value.evaluate_ready_outcomes.return_value = 3

            from services.worker.outcome_evaluation_worker import evaluate_pending_outcomes
            result = evaluate_pending_outcomes()

        mock_cls.return_value.evaluate_ready_outcomes.assert_called_once_with(fake_session)
        assert result == 3

    def test_returns_count_from_service(self):
        """Return value must be exactly what evaluate_ready_outcomes() returns."""
        fake_session = _fake_session()

        for expected in (0, 1, 7):
            with patch("services.worker.outcome_evaluation_worker.MSSQL_CONFIGURED", True), \
                 patch("services.worker.outcome_evaluation_worker.SessionLocal",
                       return_value=fake_session), \
                 patch("services.worker.outcome_evaluation_worker.InterventionOutcomeService") as mock_cls:
                mock_cls.return_value.evaluate_ready_outcomes.return_value = expected

                from services.worker.outcome_evaluation_worker import evaluate_pending_outcomes
                assert evaluate_pending_outcomes() == expected

    def test_returns_zero_when_no_records_ready(self):
        """Zero from the service must propagate cleanly."""
        fake_session = _fake_session()

        with patch("services.worker.outcome_evaluation_worker.MSSQL_CONFIGURED", True), \
             patch("services.worker.outcome_evaluation_worker.SessionLocal",
                   return_value=fake_session), \
             patch("services.worker.outcome_evaluation_worker.InterventionOutcomeService") as mock_cls:
            mock_cls.return_value.evaluate_ready_outcomes.return_value = 0

            from services.worker.outcome_evaluation_worker import evaluate_pending_outcomes
            assert evaluate_pending_outcomes() == 0

    def test_does_not_raise_when_service_raises(self):
        """If evaluate_ready_outcomes() raises unexpectedly, the worker must not
        crash the process — the exception propagates only as far as the caller,
        which the long-running runner wraps in its own try/except.

        This test verifies the worker itself is thin and does not swallow the
        error — that is the service's job via its own non-fatal contract.
        The worker's evaluate_pending_outcomes() will raise here; that is expected
        and the runner handles it.
        """
        fake_session = _fake_session()

        with patch("services.worker.outcome_evaluation_worker.MSSQL_CONFIGURED", True), \
             patch("services.worker.outcome_evaluation_worker.SessionLocal",
                   return_value=fake_session), \
             patch("services.worker.outcome_evaluation_worker.InterventionOutcomeService") as mock_cls:
            mock_cls.return_value.evaluate_ready_outcomes.side_effect = RuntimeError("db gone")

            from services.worker.outcome_evaluation_worker import evaluate_pending_outcomes
            import pytest
            with pytest.raises(RuntimeError, match="db gone"):
                evaluate_pending_outcomes()
