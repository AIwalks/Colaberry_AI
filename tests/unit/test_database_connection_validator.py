"""Unit tests for DatabaseConnectionValidator and SentinelWriteAttemptError.

All tests run without a real database — connectivity checks are exercised
through a mock SQLAlchemy engine so the suite stays hermetic and fast.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.database_connection_validator import (
    ConnectionValidationResult,
    DatabaseConnectionValidator,
    SentinelWriteAttemptError,
    _WRITE_KEYWORDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(raises: Exception | None = None):
    """Return a mock SQLAlchemy engine whose connect() context manager
    either succeeds silently or raises the given exception."""
    engine = MagicMock()
    conn_ctx = MagicMock()
    if raises:
        conn_ctx.__enter__ = MagicMock(side_effect=raises)
    else:
        conn_ctx.__enter__ = MagicMock(return_value=MagicMock())
    conn_ctx.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = conn_ctx
    return engine


def _make_engine_with_tables(table_names: list[str]):
    """Return an engine that reports the given tables from INFORMATION_SCHEMA."""
    engine = MagicMock()
    conn_ctx = MagicMock()
    mock_conn = MagicMock()
    rows = [(name,) for name in table_names]
    mock_conn.execute.return_value.fetchall.return_value = rows
    conn_ctx.__enter__ = MagicMock(return_value=mock_conn)
    conn_ctx.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = conn_ctx
    return engine


# ---------------------------------------------------------------------------
# validate_sql_is_select_only
# ---------------------------------------------------------------------------


class TestValidateSqlIsSelectOnly:
    def setup_method(self):
        self.v = DatabaseConnectionValidator()

    def test_select_passes(self):
        self.v.validate_sql_is_select_only("SELECT * FROM Students")

    def test_select_lowercase_passes(self):
        self.v.validate_sql_is_select_only("select id from foo")

    def test_select_with_leading_whitespace_passes(self):
        self.v.validate_sql_is_select_only("   SELECT id FROM bar")

    def test_with_clause_passes(self):
        self.v.validate_sql_is_select_only("WITH cte AS (SELECT 1) SELECT * FROM cte")

    def test_insert_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("INSERT INTO foo VALUES (1)")

    def test_update_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("UPDATE foo SET x = 1")

    def test_delete_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("DELETE FROM foo WHERE id = 1")

    def test_drop_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("DROP TABLE foo")

    def test_create_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("CREATE TABLE foo (id INT)")

    def test_alter_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("ALTER TABLE foo ADD COLUMN bar INT")

    def test_truncate_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("TRUNCATE TABLE foo")

    def test_exec_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("EXEC sp_rename 'foo', 'bar'")

    def test_execute_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("EXECUTE sp_help")

    def test_merge_raises(self):
        with pytest.raises(SentinelWriteAttemptError):
            self.v.validate_sql_is_select_only("MERGE INTO foo USING bar ON foo.id = bar.id")

    def test_error_message_contains_token(self):
        with pytest.raises(SentinelWriteAttemptError, match="INSERT"):
            self.v.validate_sql_is_select_only("INSERT INTO foo VALUES (1)")

    def test_comment_stripped_before_check(self):
        # Block comment removed → first real token is SELECT
        self.v.validate_sql_is_select_only("/* admin comment */ SELECT 1")

    def test_inline_comment_stripped(self):
        self.v.validate_sql_is_select_only("-- this is a comment\nSELECT 1")

    def test_all_write_keywords_covered(self):
        for kw in _WRITE_KEYWORDS:
            with pytest.raises(SentinelWriteAttemptError):
                self.v.validate_sql_is_select_only(f"{kw} something")


# ---------------------------------------------------------------------------
# validate_connectivity
# ---------------------------------------------------------------------------


class TestValidateConnectivity:
    def test_success_with_working_engine(self):
        engine = _make_engine()
        v = DatabaseConnectionValidator(engine=engine)
        ok, err = v.validate_connectivity()
        assert ok is True
        assert err is None

    def test_failure_when_engine_raises(self):
        engine = _make_engine(raises=Exception("Connection refused"))
        v = DatabaseConnectionValidator(engine=engine)
        ok, err = v.validate_connectivity()
        assert ok is False
        assert "Connection refused" in err

    def test_failure_when_no_engine(self):
        v = DatabaseConnectionValidator(engine=None)
        ok, err = v.validate_connectivity()
        assert ok is False
        assert err is not None


# ---------------------------------------------------------------------------
# validate_required_tables
# ---------------------------------------------------------------------------


class TestValidateRequiredTables:
    def test_all_tables_present(self):
        required = [
            "AIInterpretations", "GovernanceReviews", "Students", "Enrollments",
            "LearnerActivities", "AssessmentResults", "EngagementLogs",
        ]
        engine = _make_engine_with_tables(required)
        v = DatabaseConnectionValidator(engine=engine)
        present, missing = v.validate_required_tables()
        assert set(present) == set(required)
        assert missing == []

    def test_one_table_missing(self):
        have = [
            "AIInterpretations", "GovernanceReviews", "Students", "Enrollments",
            "LearnerActivities", "AssessmentResults",
            # "EngagementLogs" intentionally absent
        ]
        engine = _make_engine_with_tables(have)
        v = DatabaseConnectionValidator(engine=engine)
        present, missing = v.validate_required_tables()
        assert "EngagementLogs" in missing
        assert "AIInterpretations" in present

    def test_no_engine_returns_all_missing(self):
        v = DatabaseConnectionValidator(engine=None)
        present, missing = v.validate_required_tables()
        assert present == []
        assert len(missing) == 7

    def test_engine_query_exception_returns_all_missing(self):
        engine = _make_engine(raises=Exception("timeout"))
        v = DatabaseConnectionValidator(engine=engine)
        present, missing = v.validate_required_tables()
        assert present == []
        assert len(missing) == 7


# ---------------------------------------------------------------------------
# validate_read_only_guard
# ---------------------------------------------------------------------------


class TestValidateReadOnlyGuard:
    def test_guard_is_active(self):
        v = DatabaseConnectionValidator()
        ok, err = v.validate_read_only_guard()
        assert ok is True
        assert err is None

    def test_guard_fails_if_blocked(self, monkeypatch):
        v = DatabaseConnectionValidator()
        monkeypatch.setattr(v, "validate_sql_is_select_only", lambda sql: None)
        ok, err = v.validate_read_only_guard()
        assert ok is False
        assert "did not raise" in err


# ---------------------------------------------------------------------------
# run_full_validation
# ---------------------------------------------------------------------------


class TestRunFullValidation:
    def _all_tables_engine(self):
        required = [
            "AIInterpretations", "GovernanceReviews", "Students", "Enrollments",
            "LearnerActivities", "AssessmentResults", "EngagementLogs",
        ]
        return _make_engine_with_tables(required)

    def test_passes_with_full_setup(self):
        engine = self._all_tables_engine()
        v = DatabaseConnectionValidator(engine=engine)
        result = v.run_full_validation()
        assert isinstance(result, ConnectionValidationResult)
        assert result.connected is True
        assert result.tables_missing == []
        assert result.write_guard_ok is True
        assert result.passed is True
        assert result.errors == []

    def test_fails_with_no_engine(self):
        v = DatabaseConnectionValidator(engine=None)
        result = v.run_full_validation()
        assert result.connected is False
        assert result.passed is False
        assert len(result.errors) >= 1

    def test_fails_with_missing_tables(self):
        engine = _make_engine_with_tables(["AIInterpretations"])
        v = DatabaseConnectionValidator(engine=engine)
        result = v.run_full_validation()
        assert len(result.tables_missing) > 0
        assert result.passed is False

    def test_result_passed_property(self):
        r = ConnectionValidationResult(
            connected=True,
            tables_present=["AIInterpretations"],
            tables_missing=[],
            write_guard_ok=True,
            errors=[],
        )
        assert r.passed is True

    def test_result_not_passed_when_errors(self):
        r = ConnectionValidationResult(
            connected=True,
            tables_present=[],
            tables_missing=[],
            write_guard_ok=True,
            errors=["something went wrong"],
        )
        assert r.passed is False


# ---------------------------------------------------------------------------
# SentinelExtractionService mock fallback
# ---------------------------------------------------------------------------


class TestExtractionServiceMockFallback:
    def test_mock_returns_four_dimensions(self):
        from services.sentinel_extraction_service import SentinelExtractionService
        svc = SentinelExtractionService(use_mock=True)
        result = svc.extract_student_state(db=None, entity_id="student_101", entity_type="student")
        assert "dimensions" in result
        dims = result["dimensions"]
        assert set(dims.keys()) == {
            "engagement",
            "retention_risk",
            "communication_responsiveness",
            "intervention_effectiveness",
        }

    def test_mock_dimensions_have_required_keys(self):
        from services.sentinel_extraction_service import SentinelExtractionService
        svc = SentinelExtractionService(use_mock=True)
        result = svc.extract_student_state(db=None, entity_id="student_101", entity_type="student")
        for dim_data in result["dimensions"].values():
            assert "signals" in dim_data
            assert "risk_level" in dim_data
            assert "confidence" in dim_data
            assert "data_available" in dim_data

    def test_mock_entity_id_passthrough(self):
        from services.sentinel_extraction_service import SentinelExtractionService
        svc = SentinelExtractionService(use_mock=True)
        result = svc.extract_student_state(db=None, entity_id="student_xyz", entity_type="student")
        assert result["entity_id"] == "student_xyz"

    def test_mock_source_tables_is_mock_sentinel(self):
        from services.sentinel_extraction_service import SentinelExtractionService
        svc = SentinelExtractionService(use_mock=True)
        result = svc.extract_student_state(db=None, entity_id="x", entity_type="student")
        assert result["source_tables"] == ["mock"]

    def test_live_mode_default_is_false(self):
        from services.sentinel_extraction_service import SentinelExtractionService
        svc = SentinelExtractionService()
        assert svc._use_mock is False
