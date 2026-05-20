"""SQL Server database configuration — SQLAlchemy 2.x + pyodbc.

Connection URL priority:
  1. MSSQL_DATABASE_URL (full DSN, existing behaviour)
  2. Individual vars: MSSQL_SERVER, MSSQL_DATABASE, MSSQL_USERNAME, MSSQL_PASSWORD,
     MSSQL_DRIVER (default "ODBC Driver 17 for SQL Server")
  3. SQLite fallback (local.db) — always available so engine is never None.

Sentinel shadow-mode flags:
  MSSQL_CONFIGURED   — True when a real MSSQL connection is wired up
  SENTINEL_SHADOW_MODE — opt-in flag (env var "SENTINEL_SHADOW_MODE=true")
  SENTINEL_LIVE      — True only when both flags are set; gates live DB reads

Use MSSQL_CONFIGURED to distinguish "real DB" from "SQLite fallback" when
deciding whether to use DB-backed vs stub services.
"""

import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------------------------
# Individual MSSQL env vars (alternative to full DSN)
# ---------------------------------------------------------------------------

_MSSQL_SERVER: str = os.environ.get("MSSQL_SERVER", "")
_MSSQL_DATABASE: str = os.environ.get("MSSQL_DATABASE", "")
_MSSQL_USERNAME: str = os.environ.get("MSSQL_USERNAME", "")
_MSSQL_PASSWORD: str = os.environ.get("MSSQL_PASSWORD", "")
_MSSQL_DRIVER: str = os.environ.get("MSSQL_DRIVER", "ODBC Driver 17 for SQL Server")


def _build_mssql_url_from_parts() -> str | None:
    """Build a pyodbc connection URL from individual env vars.

    Returns None if any required var is missing.
    """
    if not all([_MSSQL_SERVER, _MSSQL_DATABASE, _MSSQL_USERNAME, _MSSQL_PASSWORD]):
        return None
    driver_encoded = quote_plus(_MSSQL_DRIVER)
    user = quote_plus(_MSSQL_USERNAME)
    pwd = quote_plus(_MSSQL_PASSWORD)
    return (
        f"mssql+pyodbc://{user}:{pwd}@{_MSSQL_SERVER}/{_MSSQL_DATABASE}"
        f"?driver={driver_encoded}&TrustServerCertificate=yes&Encrypt=yes"
    )


# ---------------------------------------------------------------------------
# Resolve final DATABASE_URL and MSSQL_CONFIGURED
# ---------------------------------------------------------------------------

_full_dsn: str | None = os.environ.get("MSSQL_DATABASE_URL") or _build_mssql_url_from_parts()

MSSQL_CONFIGURED: bool = bool(_full_dsn)
DATABASE_URL: str = _full_dsn or "sqlite:///./local.db"

# ---------------------------------------------------------------------------
# Sentinel shadow-mode flags
# ---------------------------------------------------------------------------

SENTINEL_SHADOW_MODE: bool = os.environ.get("SENTINEL_SHADOW_MODE", "").lower() == "true"
SENTINEL_LIVE: bool = MSSQL_CONFIGURED and SENTINEL_SHADOW_MODE

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)

Base = declarative_base()


from sqlalchemy.orm import Session


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
