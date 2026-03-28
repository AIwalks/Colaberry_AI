"""SQL Server database configuration — SQLAlchemy 2.x + pyodbc.

Connection URL is loaded exclusively from the environment variable
MSSQL_DATABASE_URL (never hardcoded).

Example DSN (set via environment variable, never hardcoded):
    mssql+pyodbc://<user>:<password>@<server>/<dbname>?driver=ODBC+Driver+17+for+SQL+Server

When MSSQL_DATABASE_URL is not set, the module falls back to a local SQLite
database (local.db) so that engine and SessionLocal are always initialised.

Use MSSQL_CONFIGURED to distinguish "real DB" from "SQLite fallback" when
deciding whether to use DB-backed vs stub services.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

MSSQL_CONFIGURED: bool = bool(os.environ.get("MSSQL_DATABASE_URL"))
DATABASE_URL: str = os.environ.get("MSSQL_DATABASE_URL") or "sqlite:///./local.db"

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
