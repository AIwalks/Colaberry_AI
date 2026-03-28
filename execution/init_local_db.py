"""Initialize the local SQLite database schema.

Usage:
    python execution/init_local_db.py

Creates all tables defined by SQLAlchemy ORM models.
Safe to rerun — create_all skips tables that already exist.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.database import Base, engine
import services.models  # noqa: F401 — registers all ORM models against Base

Base.metadata.create_all(bind=engine)

print("Local database initialized.")
print(f"Tables created in: {engine.url}")
