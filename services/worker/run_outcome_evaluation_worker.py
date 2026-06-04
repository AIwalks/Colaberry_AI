"""Long-running process — polls for evaluable outcome records every 300 seconds.

Outcomes only become evaluable after a 14-day window, so a 5-minute polling
interval is more than sufficient without burning unnecessary DB connections.

Run:
    python services/worker/run_outcome_evaluation_worker.py

Stop:
    Ctrl+C
"""

import time

from services.worker.outcome_evaluation_worker import evaluate_pending_outcomes

_POLL_INTERVAL_SECONDS = 300


def main() -> None:
    print("Outcome evaluation worker started. Press Ctrl+C to stop.")
    while True:
        try:
            evaluated = evaluate_pending_outcomes()
            if evaluated:
                print(f"Evaluated {evaluated} pending outcome(s).")
            time.sleep(_POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nOutcome evaluation worker stopped.")
            break


if __name__ == "__main__":
    main()
