"""Test that student status fetcher can be overridden via FastAPI DI."""

from fastapi.testclient import TestClient

from app.main import app, get_student_status_fetcher


class FakeStatusFetcher:
    def fetch_status(self, student_id: str) -> dict[str, str]:
        return {"lifecycle_stage": "active", "summary": "Test override working"}


VALID_BODY = {
    "student_id": "stu-001",
    "channel": "web",
    "message": "Hello",
}


def test_dependency_override_replaces_student_status():
    app.dependency_overrides[get_student_status_fetcher] = FakeStatusFetcher
    try:
        client = TestClient(app)
        resp = client.post("/ai/mentor/message", json=VALID_BODY)
        assert resp.status_code == 200
        status = resp.json()["student_status"]
        assert status["lifecycle_stage"] == "active"
        assert status["summary"] == "Test override working"
    finally:
        app.dependency_overrides.clear()
