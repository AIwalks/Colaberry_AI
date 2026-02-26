"""Protocol and stub for student status lookup."""

from typing import Protocol


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
