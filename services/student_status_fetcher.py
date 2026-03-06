"""Protocol and stub for student status lookup, plus real DB-backed fetcher."""

from typing import Protocol

from config.database import SessionLocal
from services.models import TriggerData


class StudentStatusFetcher(Protocol):
    """Interface for retrieving a student's lifecycle status."""

    def fetch_status(self, student_id: str) -> dict[str, str]: ...


class StubStudentStatusFetcher:
    """Deterministic stub — returns hardcoded placeholder values."""

    def fetch_status(self, student_id: str) -> dict[str, str]:
        prefix = student_id[:1].upper()
        if prefix == "A":
            return {
                "lifecycle_stage": "active",
                "summary": "Student is currently active (deterministic rule).",
            }
        if prefix == "I":
            return {
                "lifecycle_stage": "inactive",
                "summary": "Student is currently inactive (deterministic rule).",
            }
        return {
            "lifecycle_stage": "unknown",
            "summary": "Student status unknown (deterministic rule).",
        }


class DbStudentStatusFetcher:
    """Live database-backed student fetcher using AI_ChatBot_TriggerData.

    Requires MSSQL_DATABASE_URL to be set in the environment so that
    SessionLocal is available (config.database initialises it only when
    the env var is present).

    Method
    ------
    get_student(student_id)
        Converts student_id → integer UserID, queries TriggerData, and
        returns a normalised dictionary of student fields.

    Raises
    ------
    RuntimeError
        If SessionLocal is None (MSSQL_DATABASE_URL not configured).
    ValueError("student_id must be a valid integer")
        If student_id cannot be parsed as an integer.
    ValueError("Student not found")
        If no row exists in AI_ChatBot_TriggerData for that UserID.
    """

    def get_student(self, student_id: str) -> dict:
        if SessionLocal is None:
            raise RuntimeError(
                "Database session is not configured. "
                "Set MSSQL_DATABASE_URL before calling DbStudentStatusFetcher."
            )

        try:
            user_id = int(student_id)
        except (ValueError, TypeError):
            raise ValueError(
                f"student_id must be a valid integer, got {student_id!r}"
            )

        with SessionLocal() as session:
            row: TriggerData | None = session.get(TriggerData, user_id)

        if row is None:
            raise ValueError("Student not found")

        return {
            "user_id": row.UserID,
            "username": row.UserName,
            "email": row.Email,
            "phone": row.PhoneNumber,
            "active_status": row.ActiveStatus,
            "status_summary": row.StatusII,
        }
