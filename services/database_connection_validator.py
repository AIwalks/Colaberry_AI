"""Read-only database connection validator for Sentinel shadow-mode.

Responsibilities:
- Verify MSSQL connectivity
- Confirm required Sentinel tables exist
- Enforce write-blocking: raise SentinelWriteAttemptError if any write SQL
  is detected before execution

This validator never modifies the database. It is safe to run on startup.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Write-blocking constants
# ---------------------------------------------------------------------------

_WRITE_KEYWORDS: frozenset[str] = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE",
    "ALTER", "TRUNCATE", "EXEC", "EXECUTE", "MERGE",
})

_SENTINEL_TABLES: tuple[str, ...] = (
    "AIInterpretations",
    "GovernanceReviews",
    "Students",
    "Enrollments",
    "LearnerActivities",
    "AssessmentResults",
    "EngagementLogs",
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SentinelWriteAttemptError(Exception):
    """Raised when write SQL is detected in a read-only Sentinel context."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ConnectionValidationResult:
    connected: bool = False
    tables_present: list[str] = field(default_factory=list)
    tables_missing: list[str] = field(default_factory=list)
    write_guard_ok: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.connected and not self.tables_missing and self.write_guard_ok and not self.errors


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class DatabaseConnectionValidator:
    """Validates Sentinel read-only database access.

    Parameters
    ----------
    engine:
        A SQLAlchemy engine. Pass None to run in mock/offline mode; all
        connectivity checks will report as disconnected.
    """

    def __init__(self, engine=None) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Write-blocking guard
    # ------------------------------------------------------------------

    def validate_sql_is_select_only(self, sql: str) -> None:
        """Raise SentinelWriteAttemptError if *sql* contains a write keyword.

        Detection: strip leading whitespace and comments, normalise to
        uppercase, extract the first token, compare against _WRITE_KEYWORDS.
        """
        normalised = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
        normalised = re.sub(r"--[^\n]*", " ", normalised)
        first_token = normalised.strip().split()[0].upper() if normalised.strip() else ""
        if first_token in _WRITE_KEYWORDS:
            raise SentinelWriteAttemptError(
                f"Write SQL detected in read-only Sentinel context: first token '{first_token}'"
            )

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def validate_connectivity(self) -> tuple[bool, Optional[str]]:
        """Return (True, None) on success or (False, error_message) on failure."""
        if self._engine is None:
            return False, "No engine configured"
        try:
            from sqlalchemy import text
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, None
        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # Table presence
    # ------------------------------------------------------------------

    def validate_required_tables(self) -> tuple[list[str], list[str]]:
        """Return (present, missing) lists for the required Sentinel tables.

        Queries INFORMATION_SCHEMA.TABLES — works on MSSQL and most RDBMS.
        Returns ([], list_of_all_tables) when engine is None.
        """
        if self._engine is None:
            return [], list(_SENTINEL_TABLES)

        try:
            from sqlalchemy import text
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'")
                ).fetchall()
            existing = {row[0] for row in rows}
            present = [t for t in _SENTINEL_TABLES if t in existing]
            missing = [t for t in _SENTINEL_TABLES if t not in existing]
            return present, missing
        except Exception as exc:
            logger.warning("Table validation query failed: %s", exc)
            return [], list(_SENTINEL_TABLES)

    # ------------------------------------------------------------------
    # Write-guard self-test
    # ------------------------------------------------------------------

    def validate_read_only_guard(self) -> tuple[bool, Optional[str]]:
        """Confirm the write-blocking guard raises on a known write statement."""
        try:
            self.validate_sql_is_select_only("INSERT INTO foo VALUES (1)")
            return False, "Write guard did not raise on INSERT"
        except SentinelWriteAttemptError:
            return True, None

    # ------------------------------------------------------------------
    # Full validation run
    # ------------------------------------------------------------------

    def run_full_validation(self) -> ConnectionValidationResult:
        """Run all checks and return an aggregated result."""
        result = ConnectionValidationResult()

        connected, conn_err = self.validate_connectivity()
        result.connected = connected
        if conn_err:
            result.errors.append(f"connectivity: {conn_err}")

        present, missing = self.validate_required_tables()
        result.tables_present = present
        result.tables_missing = missing
        if missing:
            result.errors.append(f"missing tables: {', '.join(missing)}")

        guard_ok, guard_err = self.validate_read_only_guard()
        result.write_guard_ok = guard_ok
        if guard_err:
            result.errors.append(f"write guard: {guard_err}")

        if result.passed:
            logger.info("Sentinel DB validation passed — %d/%d tables present", len(present), len(_SENTINEL_TABLES))
        else:
            logger.warning("Sentinel DB validation issues: %s", "; ".join(result.errors))

        return result
