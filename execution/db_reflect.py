"""Reflect and print the schema of the connected SQL Server database.

Reads the database URL from the MSSQL_DATABASE_URL environment variable.
Outputs a JSON-formatted schema: table names, column names, and column types.

Usage:
    MSSQL_DATABASE_URL="mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server" \
        python execution/db_reflect.py
"""

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make config.database importable when run from any working directory
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Guard: fail early and clearly if the env var is not set
# ---------------------------------------------------------------------------
if not os.environ.get("MSSQL_DATABASE_URL"):
    print("ERROR: MSSQL_DATABASE_URL environment variable is not set.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Set it before running:", file=sys.stderr)
    print(
        '  MSSQL_DATABASE_URL="mssql+pyodbc://user:pass@server/db'
        '?driver=ODBC+Driver+17+for+SQL+Server" python execution/db_reflect.py',
        file=sys.stderr,
    )
    sys.exit(1)

from sqlalchemy import inspect as sa_inspect  # noqa: E402

from config.database import engine  # noqa: E402


def reflect_schema(eng) -> dict:
    """Inspect the live database and return a structured schema dict.

    Returns:
        {
            "table_name": {
                "columns": [
                    {"name": "col", "type": "VARCHAR(100)", "nullable": True},
                    ...
                ]
            },
            ...
        }
    """
    inspector = sa_inspect(eng)
    schema = {}

    for table_name in sorted(inspector.get_table_names()):
        columns = []
        for col in inspector.get_columns(table_name):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
            })
        schema[table_name] = {"columns": columns}

    return schema


if __name__ == "__main__":
    schema = reflect_schema(engine)
    print(json.dumps(schema, indent=2))
