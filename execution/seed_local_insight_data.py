"""Seed local SQLite with sample data for the insight flow.

Usage:
    python execution/init_local_db.py   # create tables first
    python execution/seed_local_insight_data.py

Idempotency strategy: deletes all existing rows from DiscoveredKPI and
BehaviorFingerprint before inserting. Safe for local development — no
production guard needed because this script only runs against the SQLite
fallback (MSSQL_DATABASE_URL absent). If MSSQL_DATABASE_URL is set,
the script exits immediately to prevent accidental writes to a real database.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if os.environ.get("MSSQL_DATABASE_URL"):
    print("ERROR: MSSQL_DATABASE_URL is set. This script is for local SQLite only.")
    sys.exit(1)

from config.database import SessionLocal
import services.models  # noqa: F401 — registers all ORM models against Base
from services.models import BehaviorFingerprint, DiscoveredKPI

db = SessionLocal()

try:
    # Clear existing rows so reruns produce a predictable state.
    db.query(DiscoveredKPI).delete()
    db.query(BehaviorFingerprint).delete()
    db.commit()

    kpis = [
        # confidence > 0.7 — will produce a "kpi" insight
        DiscoveredKPI(
            kpi_name="avg_logins_per_week",
            source_pattern="disengagement",
            entity_type="student",
            formula="AVG(logins) OVER (PARTITION BY student_id)",
            confidence=0.92,
            sample_size=120,
        ),
        # confidence > 0.7 — will produce a "kpi" insight
        DiscoveredKPI(
            kpi_name="session_duration_drop",
            source_pattern="dropout_risk",
            entity_type="student",
            formula="(prev_avg_duration - curr_avg_duration) / prev_avg_duration",
            confidence=0.81,
            sample_size=85,
        ),
        # confidence <= 0.7 — will NOT produce an insight (below threshold)
        DiscoveredKPI(
            kpi_name="support_ticket_rate",
            source_pattern="struggling_learner",
            entity_type="student",
            formula="COUNT(tickets) / active_days",
            confidence=0.55,
            sample_size=40,
        ),
    ]

    fingerprints = [
        # risk_level == "high" — will produce a "risk" insight
        BehaviorFingerprint(
            entity_type="student",
            entity_id="student_101",
            pattern_name="disengagement",
            score=1.0,
            risk_level="high",
            details_json='{"matched": 3, "total": 3, "metrics": {"logins": 1, "sessions": 0, "duration": 2}}',
        ),
        # risk_level == "medium" — will NOT produce an insight
        BehaviorFingerprint(
            entity_type="student",
            entity_id="student_202",
            pattern_name="struggling_learner",
            score=0.5,
            risk_level="medium",
            details_json='{"matched": 1, "total": 2, "metrics": {"support_tickets": 3}}',
        ),
    ]

    db.add_all(kpis)
    db.add_all(fingerprints)
    db.commit()

    kpi_count = db.query(DiscoveredKPI).count()
    fp_count = db.query(BehaviorFingerprint).count()

    print(f"Seeded {kpi_count} DiscoveredKPI rows ({sum(1 for k in kpis if k.confidence > 0.7)} will generate insights).")
    print(f"Seeded {fp_count} BehaviorFingerprint rows ({sum(1 for f in fingerprints if f.risk_level == 'high')} will generate insights).")
    print("Expected insights on next POST /insight/generate: 3 (2 kpi + 1 risk).")

finally:
    db.close()
