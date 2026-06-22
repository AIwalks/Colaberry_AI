"""Unit tests for migration 0015 — repair AI_ChatBot_StudentResponses.

Runs entirely in-memory (SQLite) — no SQL Server required.

Uses Alembic's own Operations class with a real SQLite connection so the
migration code path is exercised without any stubs.

Tests verify:
  - Schema drift scenario (table absent): migration creates table + all 3 indexes
  - Idempotent scenario (table already present): second upgrade does not error
  - Partial-repair scenario: migration adds missing indexes when table exists
  - Downgrade: drops table and indexes cleanly
  - matched_at is nullable: column accepts NULL (code-to-schema alignment fix)
  - Migration metadata (revision chain)
"""

import importlib.util
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text


# ---------------------------------------------------------------------------
# Load migration module
# ---------------------------------------------------------------------------

_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "0015_repair_student_responses_table.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0015", _MIGRATION_PATH)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_migration = _load_migration()

_TABLE   = "AI_ChatBot_StudentResponses"
_INDEXES = {
    "ix_student_responses_cbm_id",
    "ix_student_responses_engagement_event_id",
    "ix_student_responses_user_id",
}


# ---------------------------------------------------------------------------
# Helper: SQLite engine that stays alive for the whole test
# ---------------------------------------------------------------------------

@contextmanager
def _sqlite_ops():
    """Yield (connection, Alembic Operations) backed by an in-memory SQLite DB.

    The connection is kept open so the in-memory schema persists for the
    duration of the `with` block.  Each call returns a fresh empty database.
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op  = Operations(ctx)
        # Inject the real Alembic Operations object into the migration module
        _migration.__dict__["op"] = op
        yield conn, op


def _has_table(conn) -> bool:
    return inspect(conn).has_table(_TABLE)


def _index_names(conn) -> set:
    if not _has_table(conn):
        return set()
    return {idx["name"] for idx in inspect(conn).get_indexes(_TABLE)}


def _column_nullable(conn, col_name: str) -> bool:
    for col in inspect(conn).get_columns(_TABLE):
        if col["name"] == col_name:
            return col.get("nullable", True)
    raise KeyError(col_name)


# ---------------------------------------------------------------------------
# Tests — Schema Drift Scenario (table absent)
# ---------------------------------------------------------------------------

class TestTableAbsent:
    """Simulates production drift: alembic_version=0014 but table is missing."""

    def test_table_created_on_upgrade(self):
        with _sqlite_ops() as (conn, _):
            assert not _has_table(conn)
            _migration.upgrade()
            conn.commit()
            assert _has_table(conn)

    def test_all_three_indexes_created(self):
        with _sqlite_ops() as (conn, _):
            _migration.upgrade()
            conn.commit()
            missing = _INDEXES - _index_names(conn)
            assert not missing, f"Missing indexes: {missing}"

    def test_required_columns_present(self):
        with _sqlite_ops() as (conn, _):
            _migration.upgrade()
            conn.commit()
            cols = {c["name"] for c in inspect(conn).get_columns(_TABLE)}
            required = {
                "id", "cbm_id", "engagement_event_id", "user_id",
                "response_channel", "match_method", "confidence", "matched_at",
            }
            assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_matched_at_is_nullable(self):
        """matched_at must accept NULL — aligns with serializer + frontend type."""
        with _sqlite_ops() as (conn, _):
            _migration.upgrade()
            conn.commit()
            assert _column_nullable(conn, "matched_at") is True

    def test_row_insert_with_null_matched_at(self):
        with _sqlite_ops() as (conn, _):
            _migration.upgrade()
            conn.commit()
            conn.execute(
                text(
                    f"INSERT INTO {_TABLE} "
                    "(cbm_id, engagement_event_id, user_id, response_channel, match_method, confidence, matched_at) "
                    "VALUES (1, 100, 101, 'whatsapp', 'thread_id', 1.0, NULL)"
                )
            )
            conn.commit()
            row = conn.execute(
                text(f"SELECT matched_at FROM {_TABLE} WHERE cbm_id = 1")
            ).fetchone()
            assert row[0] is None

    def test_row_insert_with_timestamp(self):
        with _sqlite_ops() as (conn, _):
            _migration.upgrade()
            conn.commit()
            conn.execute(
                text(
                    f"INSERT INTO {_TABLE} "
                    "(cbm_id, engagement_event_id, user_id, response_channel, match_method, confidence, matched_at) "
                    "VALUES (42, 1001, 101, 'whatsapp', 'thread_id', 1.0, '2026-06-20 14:30:00')"
                )
            )
            conn.commit()
            n = conn.execute(text(f"SELECT COUNT(*) FROM {_TABLE}")).scalar()
            assert n == 1


# ---------------------------------------------------------------------------
# Tests — Idempotent Scenario (table already present)
# ---------------------------------------------------------------------------

class TestIdempotent:
    """Table and indexes already exist — second upgrade must not raise."""

    def test_second_upgrade_does_not_raise(self):
        with _sqlite_ops() as (conn, _):
            _migration.upgrade()
            conn.commit()
            # Call upgrade a second time — must be safe
            _migration.upgrade()
            conn.commit()

    def test_index_count_unchanged_after_second_upgrade(self):
        with _sqlite_ops() as (conn, _):
            _migration.upgrade()
            conn.commit()
            before = _index_names(conn)
            _migration.upgrade()
            conn.commit()
            after = _index_names(conn)
            assert before == after


# ---------------------------------------------------------------------------
# Tests — Partial-Repair Scenario
# ---------------------------------------------------------------------------

class TestPartialRepair:
    """Table present but one index missing — migration should add the gap."""

    def test_missing_cbm_id_index_is_added(self):
        with _sqlite_ops() as (conn, op):
            _migration.upgrade()
            conn.commit()
            # Drop one index to simulate partial drift
            op.drop_index("ix_student_responses_cbm_id", table_name=_TABLE)
            conn.commit()
            assert "ix_student_responses_cbm_id" not in _index_names(conn)
            # Second upgrade should restore it
            _migration.upgrade()
            conn.commit()
            assert "ix_student_responses_cbm_id" in _index_names(conn)

    def test_other_indexes_not_duplicated_during_partial_repair(self):
        with _sqlite_ops() as (conn, op):
            _migration.upgrade()
            conn.commit()
            op.drop_index("ix_student_responses_cbm_id", table_name=_TABLE)
            conn.commit()
            _migration.upgrade()
            conn.commit()
            # Should have all three — no duplicates
            assert _INDEXES == _index_names(conn)


# ---------------------------------------------------------------------------
# Tests — Downgrade
# ---------------------------------------------------------------------------

class TestDowngrade:

    def test_downgrade_removes_table(self):
        with _sqlite_ops() as (conn, _):
            _migration.upgrade()
            conn.commit()
            assert _has_table(conn)
            _migration.downgrade()
            conn.commit()
            assert not _has_table(conn)

    def test_downgrade_leaves_no_orphan_indexes(self):
        with _sqlite_ops() as (conn, _):
            _migration.upgrade()
            conn.commit()
            _migration.downgrade()
            conn.commit()
            assert _index_names(conn) == set()


# ---------------------------------------------------------------------------
# Tests — Migration Metadata
# ---------------------------------------------------------------------------

class TestMigrationMetadata:

    def test_revision_is_0015(self):
        assert _migration.revision == "0015"

    def test_down_revision_is_0014(self):
        assert _migration.down_revision == "0014"
