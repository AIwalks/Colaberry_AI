"""Standalone worker — evaluates all pending InterventionOutcome records whose
evaluation window has closed.

Run directly:
    python -m services.worker.outcome_evaluation_worker

Or import and call from a scheduler or management script:
    from services.worker.outcome_evaluation_worker import evaluate_pending_outcomes
    evaluated = evaluate_pending_outcomes()
"""

from config.database import SessionLocal, MSSQL_CONFIGURED
from services.intervention_outcome_service import InterventionOutcomeService


def evaluate_pending_outcomes() -> int:
    """Score every InterventionOutcome row where outcome='pending' and window_end
    has passed.

    Opens one session, delegates all querying and per-record exception isolation
    to InterventionOutcomeService.evaluate_ready_outcomes(), then closes the
    session.

    Returns
    -------
    int — number of records transitioned out of 'pending' in this run.
          Returns 0 immediately if SessionLocal is not configured.
    """
    if not MSSQL_CONFIGURED:
        return 0

    with SessionLocal() as session:
        return InterventionOutcomeService().evaluate_ready_outcomes(session)


if __name__ == "__main__":
    evaluated = evaluate_pending_outcomes()
    print(f"Evaluated {evaluated} pending outcome(s).")
