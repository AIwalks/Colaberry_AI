# Directive: Database Safety — init_local_db.py

**Last updated:** 2026-04-12
**Covers:** `execution/init_local_db.py`, `config/database.py`
**Classification:** Safety-critical — modifications require explicit owner approval

---

## 1. Purpose

`execution/init_local_db.py` exists for one purpose only: initializing the local SQLite
development database so engineers can run the application without a SQL Server connection.

It calls `Base.metadata.create_all()` to create all tables defined by the SQLAlchemy ORM
models. It is safe to rerun locally — `create_all` skips tables that already exist.

**This script is a local developer tool. It is not a migration tool. It is not a schema
management tool. It must never be used as a way to apply schema changes to any shared or
production database.**

---

## 2. Risk — Production DDL via MSSQL_DATABASE_URL

`config/database.py` resolves the database engine at import time:

```python
DATABASE_URL = os.environ.get("MSSQL_DATABASE_URL") or "sqlite:///./local.db"
engine = create_engine(DATABASE_URL, ...)
```

When `MSSQL_DATABASE_URL` is set in the environment — as it will be on any machine
configured for staging or production — `engine` points to the SQL Server database.

Without a guard, running `python execution/init_local_db.py` in that environment would:

- Issue DDL (`CREATE TABLE`) directly against the SQL Server production database
- Create tables that exist in the ORM models but not yet in production — bypassing the
  migration system entirely
- Do this silently, with no warning, because `create_all` does not distinguish between
  local and remote databases

The script is named and documented as "local SQLite initialization." A developer following
setup instructions, or a CI runner restoring the local environment, has no reason to
suspect they are running DDL against production. The risk is silent and difficult to detect
after the fact.

---

## 3. Safety Guard

`init_local_db.py` must check `MSSQL_CONFIGURED` before allowing `create_all` to run.

### Required guard (must always be present)

```python
from config.database import Base, engine, MSSQL_CONFIGURED
import services.models  # noqa: F401

if MSSQL_CONFIGURED:
    print("ERROR: MSSQL_DATABASE_URL is set. This script only runs against the local SQLite database.")
    print("Unset MSSQL_DATABASE_URL before running init_local_db.py.")
    sys.exit(1)

Base.metadata.create_all(bind=engine)
```

### Why MSSQL_CONFIGURED

`MSSQL_CONFIGURED` is a boolean defined in `config/database.py`:

```python
MSSQL_CONFIGURED: bool = bool(os.environ.get("MSSQL_DATABASE_URL"))
```

It is the canonical indicator that the system is connected to SQL Server rather than the
local SQLite fallback. It is already used throughout the codebase to gate DB-backed
services. Using it here is consistent with the existing pattern and means the guard
reflects the same decision point as every other MSSQL-gated path.

### Why sys.exit(1) — not a warning, not a return

A `print` warning without `sys.exit` would print the message and continue. `create_all`
would still execute against production. The only guarantee that DDL does not run is a hard
exit before `create_all` is reached. Exit code `1` ensures that any shell script, CI
pipeline, or `Makefile` calling this script will surface the failure rather than continuing.

### Verified behavior

```
# With MSSQL_DATABASE_URL set:
$ MSSQL_DATABASE_URL="mssql+pyodbc://..." python execution/init_local_db.py
ERROR: MSSQL_DATABASE_URL is set. This script only runs against the local SQLite database.
Unset MSSQL_DATABASE_URL before running init_local_db.py.
$ echo $?
1

# Without MSSQL_DATABASE_URL:
$ python execution/init_local_db.py
Local database initialized.
Tables created in: sqlite:///./local.db
$ echo $?
0
```

---

## 4. Rules

### The script must never run against MSSQL

`init_local_db.py` is not a migration tool. It does not track schema versions. It does not
know which tables already exist in production or what state they are in. Running it against
SQL Server would bypass the migration system and produce an inconsistent schema state.

All schema changes to shared or production databases must go through the approved migration
path. `init_local_db.py` is not part of that path.

### The guard must remain in place at all times

The `MSSQL_CONFIGURED` guard and `sys.exit(1)` call must not be removed, commented out,
or weakened (e.g. changed to a warning). They are a non-negotiable safety control.

Acceptable changes to the guard:
- Tightening it (e.g. additional checks)
- Improving the error message
- Adding logging alongside the existing behavior

Not acceptable:
- Removing the `sys.exit(1)`
- Moving the guard below `create_all`
- Replacing it with a `print` only
- Adding a `--force` flag or any bypass mechanism

### Any modification requires explicit approval

Changes to `execution/init_local_db.py` that affect the guard behavior are
**approval-gated** under CLAUDE.md operating rule 4. They must be proposed, reviewed,
and explicitly approved before implementation. This applies to:

- Removing or loosening the guard
- Changing the condition under which the guard fires
- Adding any code path that calls `create_all` before or around the guard

---

## 5. Failure Mode — What Happens If the Guard Is Removed

If the `MSSQL_CONFIGURED` check and `sys.exit(1)` are removed:

1. The script imports `config.database`, which resolves `engine` to whichever database
   `MSSQL_DATABASE_URL` points to — silently.

2. `Base.metadata.create_all(bind=engine)` runs against that engine.

3. SQLAlchemy issues `CREATE TABLE IF NOT EXISTS` for every model registered against `Base`.

4. Any table defined in the ORM but not yet in the production database is created — without
   a migration record, without a review, and without the migration system's knowledge.

5. The script prints `"Local database initialized."` and exits `0`. The operator sees a
   success message with no indication that production was touched.

6. Future migration attempts may conflict with the manually created tables, causing
   migration failures or data loss.

The damage is silent, immediate, and difficult to roll back cleanly without inspecting
the production schema and manually dropping or altering affected tables.

---

## 6. Definition of Done

- [x] `MSSQL_CONFIGURED` guard present in `execution/init_local_db.py`
- [x] `sys.exit(1)` fires when `MSSQL_DATABASE_URL` is set
- [x] Script runs normally (exit `0`) when `MSSQL_DATABASE_URL` is absent
- [x] Both behaviors verified by manual execution
- [ ] Automated test covering guard behavior (future — see below)

### Recommended future test

```python
def test_init_local_db_refuses_when_mssql_configured(monkeypatch):
    """init_local_db exits 1 when MSSQL_DATABASE_URL is set."""
    import subprocess, sys
    env = {**os.environ, "MSSQL_DATABASE_URL": "mssql+pyodbc://fake/db"}
    result = subprocess.run(
        [sys.executable, "execution/init_local_db.py"],
        env=env,
        capture_output=True,
    )
    assert result.returncode == 1
    assert b"MSSQL_DATABASE_URL is set" in result.stdout
```
