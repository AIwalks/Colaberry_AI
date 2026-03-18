"""Long-running process — polls for pending triggers every 5 seconds.

Run:
    python services/worker/run_trigger_worker.py

Stop:
    Ctrl+C
"""

import time

from services.worker.trigger_worker import process_pending_triggers


def main() -> None:
    print("Trigger worker started. Press Ctrl+C to stop.")
    while True:
        try:
            processed = process_pending_triggers()
            if processed:
                print(f"Processed {processed} pending trigger(s).")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\nTrigger worker stopped.")
            break


if __name__ == "__main__":
    main()
