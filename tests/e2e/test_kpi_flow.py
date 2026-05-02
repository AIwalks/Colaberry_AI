"""End-to-end flow test for POST /kpi/discover.

Uses the real route, real KPIDiscoveryService, and real KPIDiscoveryAnalyzer.
The DB session is replaced with a configurable fake that controls which
fingerprint rows the service reads, without touching any external service.

No mocks on the service or analyzer layer — this test exercises the full
in-process call chain:

    TestClient → route → KPIDiscoveryService → KPIDiscoveryAnalyzer → fake DB
"""

from fastapi.testclient import TestClient

from app.main import app
from config.database import get_db


# ---------------------------------------------------------------------------
# Fake DB infrastructure
#
# FakeQuery wraps a list so db.query(Model).all() works without a real engine.
# FakeSession is configurable per test — pass fingerprint objects in __init__.
# ---------------------------------------------------------------------------

class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    """Minimal SQLAlchemy session stand-in for KPI discovery e2e tests.

    fingerprints: list of fake ORM-like objects to return from
    db.query(BehaviorFingerprint).all(). Pass [] to simulate an empty table.
    """

    def __init__(self, fingerprints=None):
        self._fingerprints = fingerprints if fingerprints is not None else []
        self.committed = False

    def query(self, model):
        return FakeQuery(self._fingerprints)

    def add(self, obj):
        pass

    def commit(self):
        self.committed = True

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Fake fingerprint ORM object
# ---------------------------------------------------------------------------

class FakeFingerprint:
    def __init__(self, entity_type="student", entity_id="s1",
                 pattern_name="disengagement"):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.pattern_name = pattern_name


# ---------------------------------------------------------------------------
# Helper — override get_db for a specific test
# ---------------------------------------------------------------------------

def override_db(fingerprints):
    """Return a get_db override that yields a FakeSession with given rows."""
    def _fake_db():
        yield FakeSession(fingerprints=fingerprints)
    return _fake_db


client = TestClient(app, headers={"X-Api-Key": "test-key"})


# ---------------------------------------------------------------------------
# POST /kpi/discover returns 200
# ---------------------------------------------------------------------------

def test_discover_returns_200_with_fingerprints():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    assert resp.status_code == 200


def test_discover_returns_200_with_empty_db():
    app.dependency_overrides[get_db] = override_db([])
    resp = client.post("/kpi/discover")
    assert resp.status_code == 200


def test_discover_returns_json_content_type():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    assert "application/json" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Response contains KPI list
# ---------------------------------------------------------------------------

def test_response_contains_kpis_found_key():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    assert "kpis_found" in resp.json()


def test_response_contains_kpis_key():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    assert "kpis" in resp.json()


def test_kpis_is_a_list():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    assert isinstance(resp.json()["kpis"], list)


def test_kpis_found_is_integer():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    assert isinstance(resp.json()["kpis_found"], int)


def test_kpis_list_contains_strings():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    for item in resp.json()["kpis"]:
        assert isinstance(item, str)


def test_with_one_fingerprint_discovers_avg_logins_kpi():
    """Real analyzer always discovers avg_logins when fingerprints exist."""
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    data = resp.json()
    assert data["kpis_found"] == 1
    assert "avg_logins" in data["kpis"]


def test_kpis_found_matches_kpis_list_length():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    data = resp.json()
    assert data["kpis_found"] == len(data["kpis"])


# ---------------------------------------------------------------------------
# Empty DB returns empty list — real analyzer short-circuits on zero input
# ---------------------------------------------------------------------------

def test_empty_db_kpis_found_is_zero():
    app.dependency_overrides[get_db] = override_db([])
    resp = client.post("/kpi/discover")
    assert resp.json()["kpis_found"] == 0


def test_empty_db_kpis_is_empty_list():
    app.dependency_overrides[get_db] = override_db([])
    resp = client.post("/kpi/discover")
    assert resp.json()["kpis"] == []


def test_empty_db_response_has_required_keys():
    app.dependency_overrides[get_db] = override_db([])
    resp = client.post("/kpi/discover")
    assert "kpis_found" in resp.json()
    assert "kpis" in resp.json()


# ---------------------------------------------------------------------------
# Multiple fingerprints — analyzer still produces one avg_logins KPI
# ---------------------------------------------------------------------------

def test_multiple_fingerprints_still_returns_avg_logins():
    """Real analyzer aggregates across all rows — still produces one KPI."""
    fps = [FakeFingerprint(entity_id=f"s{i}") for i in range(5)]
    app.dependency_overrides[get_db] = override_db(fps)
    resp = client.post("/kpi/discover")
    data = resp.json()
    assert data["kpis_found"] == 1
    assert "avg_logins" in data["kpis"]


def test_multiple_fingerprints_kpis_found_matches_list():
    fps = [FakeFingerprint(entity_id=f"s{i}") for i in range(3)]
    app.dependency_overrides[get_db] = override_db(fps)
    resp = client.post("/kpi/discover")
    data = resp.json()
    assert data["kpis_found"] == len(data["kpis"])


def test_single_fingerprint_and_multiple_fingerprints_both_return_200():
    for count in (1, 3, 10):
        fps = [FakeFingerprint(entity_id=f"s{i}") for i in range(count)]
        app.dependency_overrides[get_db] = override_db(fps)
        resp = client.post("/kpi/discover")
        assert resp.status_code == 200, f"Failed with {count} fingerprints"


# ---------------------------------------------------------------------------
# Response fields valid
# ---------------------------------------------------------------------------

def test_kpis_found_is_non_negative():
    for fps in ([], [FakeFingerprint()], [FakeFingerprint(), FakeFingerprint()]):
        app.dependency_overrides[get_db] = override_db(fps)
        resp = client.post("/kpi/discover")
        assert resp.json()["kpis_found"] >= 0


def test_kpi_names_are_non_empty_strings():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    for name in resp.json()["kpis"]:
        assert isinstance(name, str) and len(name) > 0


def test_response_has_exactly_two_keys():
    app.dependency_overrides[get_db] = override_db([FakeFingerprint()])
    resp = client.post("/kpi/discover")
    assert set(resp.json().keys()) == {"kpis_found", "kpis"}
