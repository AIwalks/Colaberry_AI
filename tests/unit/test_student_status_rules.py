"""Unit tests for StubStudentStatusFetcher deterministic rules."""

from services.student_status_fetcher import StubStudentStatusFetcher


def test_student_id_prefix_a_is_active():
    result = StubStudentStatusFetcher().fetch_status("A123")
    assert result["lifecycle_stage"] == "active"
    assert "active" in result["summary"]


def test_student_id_prefix_i_is_inactive():
    result = StubStudentStatusFetcher().fetch_status("I123")
    assert result["lifecycle_stage"] == "inactive"
    assert "inactive" in result["summary"]


def test_other_prefix_is_unknown():
    result = StubStudentStatusFetcher().fetch_status("Z123")
    assert result["lifecycle_stage"] == "unknown"
    assert "unknown" in result["summary"]


def test_case_insensitive_prefix():
    fetcher = StubStudentStatusFetcher()
    assert fetcher.fetch_status("a123")["lifecycle_stage"] == "active"
    assert fetcher.fetch_status("i123")["lifecycle_stage"] == "inactive"
