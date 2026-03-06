"""Verify live SQL Server connectivity with SELECT 1.

Skipped automatically when MSSQL_DATABASE_URL is not set in the environment.
To run against a real database:

    MSSQL_DATABASE_URL="mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server" \
        pytest tests/unit/test_db_connection.py -v
"""

import os

import pytest

_DATABASE_URL = os.environ.get("MSSQL_DATABASE_URL")


@pytest.mark.skipif(
    not _DATABASE_URL,
    reason="MSSQL_DATABASE_URL not set — skipping live DB connection test",
)
def test_db_connection_select_one() -> None:
    from sqlalchemy import text

    from config.database import engine

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        row = result.fetchone()

    assert row is not None, "Expected a row from SELECT 1"
    assert row[0] == 1, f"Expected 1, got {row[0]}"
