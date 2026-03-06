"""SQL Server database configuration — SQLAlchemy 2.x + pyodbc.

Connection URL is loaded exclusively from the environment variable
MSSQL_DATABASE_URL (never hardcoded).

Example DSN:
    mssql+pyodbc://user:pass@server/dbname?driver=ODBC+Driver+17+for+SQL+Server

engine and SessionLocal are None when the env var is absent so that this
module can be safely imported during tests and Alembic metadata introspection
without a live database.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL: str | None = os.environ.get("MSSQL_DATABASE_URL")

if DATABASE_URL:
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
else:
    engine = None  # type: ignore[assignment]
    SessionLocal = None  # type: ignore[assignment]

Base = declarative_base()
