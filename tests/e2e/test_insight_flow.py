"""End-to-end flow test for POST /insight/generate.

Uses the real route, real InsightService, and real InsightGenerator.
The DB session is replaced with a configurable fake that returns controlled
KPI and fingerprint rows so the generator can be exercised without a live DB.

No mocks on the service or generator layer — this test exercises the full
in-process call chain:

    TestClient → route → InsightService → InsightGenerator → fake DB
"""

from fastapi.testclient import TestClient

from app.main import app
from config.database import get_db
from services.models import BehaviorFingerprint, DiscoveredKPI


# ---------------------------------------------------------------------------
# Fake DB infrastructure
#
# FakeQuery wraps a list so db.query(Model).all() works without a real engine.
# FakeSession dispatches to the correct list based on the model being queried.
# ---------------------------------------------------------------------------

class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    """Minimal SQLAlchemy session for insight e2e tests.

    kpis:          fake DiscoveredKPI-like objects returned by load_kpis()
    fingerprints:  fake BehaviorFingerprint-like objects returned by load_fingerprints()
    """

    def __init__(self, kpis=None, fingerprints=None):
        self._kpis = kpis if kpis is not None else []
        self._fingerprints = fingerprints if fingerprints is not None else []

    def query(self, model):
        if model is DiscoveredKPI:
            return FakeQuery(self._kpis)
        if model is BehaviorFingerprint:
            return FakeQuery(self._fingerprints)
        return FakeQuery([])

    def add(self, obj):
        pass

    def commit(self):
        pass

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Fake ORM-like objects
# ---------------------------------------------------------------------------

class FakeKPI:
    def __init__(self, kpi_name="avg_logins", confidence=0.8,
                 entity_type="student", source_pattern="auto",
                 formula="avg(logins)", sample_size=10):
        self.kpi_name = kpi_name
        self.confidence = confidence
        self.entity_type = entity_type
        self.source_pattern = source_pattern
        self.formula = formula
        self.sample_size = sample_size


class FakeFingerprint:
    def __init__(self, entity_type="student", entity_id="s1",
                 pattern_name="disengagement", score=0.9, risk_level="high"):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.pattern_name = pattern_name
        self.score = score
        self.risk_level = risk_level


# ---------------------------------------------------------------------------
# Helper — override get_db per test
# ---------------------------------------------------------------------------

def override_db(kpis=None, fingerprints=None):
    def _fake_db():
        yield FakeSession(kpis=kpis, fingerprints=fingerprints)
    return _fake_db


client = TestClient(app, headers={"X-Api-Key": "test-key"})

EXPECTED_TOP_KEYS = {"generated_count", "analyzed_kpis", "analyzed_fingerprints", "insights"}
EXPECTED_INSIGHT_KEYS = {"id", "title", "body", "insight_type", "entity_type", "entity_id", "confidence"}


# ---------------------------------------------------------------------------
# POST /insight/generate returns 200
# ---------------------------------------------------------------------------

def test_generate_returns_200_with_qualifying_kpi():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI(confidence=0.8)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.status_code == 200


def test_generate_returns_200_with_empty_db():
    app.dependency_overrides[get_db] = override_db()
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.status_code == 200


def test_generate_returns_200_with_high_risk_fingerprint():
    app.dependency_overrides[get_db] = override_db(fingerprints=[FakeFingerprint(risk_level="high")])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.status_code == 200


def test_generate_returns_json_content_type():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI()])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert "application/json" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Response contains insight list
# ---------------------------------------------------------------------------

def test_response_has_all_top_level_keys():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI()])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert set(resp.json().keys()) == EXPECTED_TOP_KEYS


def test_insights_is_a_list():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI()])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert isinstance(resp.json()["insights"], list)


def test_qualifying_kpi_produces_insight_in_list():
    """Real generator: confidence=0.8 > 0.7 threshold → one kpi insight."""
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI(confidence=0.8)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    data = resp.json()
    assert data["generated_count"] == 1
    assert len(data["insights"]) == 1


def test_high_risk_fingerprint_produces_insight_in_list():
    """Real generator: risk_level='high' → one risk insight."""
    app.dependency_overrides[get_db] = override_db(fingerprints=[FakeFingerprint(risk_level="high")])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    data = resp.json()
    assert data["generated_count"] == 1
    assert len(data["insights"]) == 1


def test_kpi_insight_type_is_kpi():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI(confidence=0.9)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["insights"][0]["insight_type"] == "kpi"


def test_risk_insight_type_is_risk():
    app.dependency_overrides[get_db] = override_db(fingerprints=[FakeFingerprint(risk_level="high")])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["insights"][0]["insight_type"] == "risk"


# ---------------------------------------------------------------------------
# Empty input handled
# ---------------------------------------------------------------------------

def test_empty_db_generated_count_is_zero():
    app.dependency_overrides[get_db] = override_db()
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["generated_count"] == 0


def test_empty_db_insights_is_empty_list():
    app.dependency_overrides[get_db] = override_db()
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["insights"] == []


def test_empty_db_analyzed_counts_are_zero():
    app.dependency_overrides[get_db] = override_db()
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    data = resp.json()
    assert data["analyzed_kpis"] == 0
    assert data["analyzed_fingerprints"] == 0


def test_low_confidence_kpi_produces_no_insight():
    """Real generator: confidence=0.5 ≤ 0.7 → no insight."""
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI(confidence=0.5)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["generated_count"] == 0


def test_medium_risk_fingerprint_produces_no_insight():
    """Real generator: risk_level='medium' ≠ 'high' → no insight."""
    app.dependency_overrides[get_db] = override_db(fingerprints=[FakeFingerprint(risk_level="medium")])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["generated_count"] == 0


# ---------------------------------------------------------------------------
# Multiple insights generated
# ---------------------------------------------------------------------------

def test_two_qualifying_kpis_produce_two_insights():
    kpis = [FakeKPI("avg_logins", 0.9), FakeKPI("avg_sessions", 0.85)]
    app.dependency_overrides[get_db] = override_db(kpis=kpis)
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    data = resp.json()
    assert data["generated_count"] == 2
    assert len(data["insights"]) == 2


def test_qualifying_kpi_and_high_risk_fp_produce_two_insights():
    app.dependency_overrides[get_db] = override_db(
        kpis=[FakeKPI(confidence=0.9)],
        fingerprints=[FakeFingerprint(risk_level="high")],
    )
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    data = resp.json()
    assert data["generated_count"] == 2
    assert len(data["insights"]) == 2


def test_mixed_qualifying_and_non_qualifying_kpis():
    """Only kpis with confidence > 0.7 generate insights."""
    kpis = [FakeKPI("avg_logins", 0.9), FakeKPI("avg_score", 0.5)]
    app.dependency_overrides[get_db] = override_db(kpis=kpis)
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["generated_count"] == 1


def test_generated_count_matches_insights_list_length():
    kpis = [FakeKPI("kpi_1", 0.9), FakeKPI("kpi_2", 0.85)]
    fps = [FakeFingerprint(risk_level="high")]
    app.dependency_overrides[get_db] = override_db(kpis=kpis, fingerprints=fps)
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    data = resp.json()
    assert data["generated_count"] == len(data["insights"])


# ---------------------------------------------------------------------------
# Response fields valid
# ---------------------------------------------------------------------------

def test_insight_has_all_expected_keys():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI(confidence=0.8)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert set(resp.json()["insights"][0].keys()) == EXPECTED_INSIGHT_KEYS


def test_insight_entity_id_is_string():
    """Service casts entity_id to str — must come back as string."""
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI(confidence=0.8)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert isinstance(resp.json()["insights"][0]["entity_id"], str)


def test_insight_confidence_is_float():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI(confidence=0.8)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert isinstance(resp.json()["insights"][0]["confidence"], float)


def test_insight_confidence_matches_kpi_confidence():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI(confidence=0.85)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["insights"][0]["confidence"] == 0.85


def test_insight_title_contains_kpi_name():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI("avg_logins", confidence=0.9)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert "avg_logins" in resp.json()["insights"][0]["title"]


def test_risk_insight_title_contains_pattern_name():
    app.dependency_overrides[get_db] = override_db(
        fingerprints=[FakeFingerprint(pattern_name="disengagement", risk_level="high")]
    )
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert "disengagement" in resp.json()["insights"][0]["title"]


# ---------------------------------------------------------------------------
# Counts and IDs valid
# ---------------------------------------------------------------------------

def test_analyzed_kpis_reflects_input_count():
    kpis = [FakeKPI("k1", 0.9), FakeKPI("k2", 0.5)]  # 2 total, only 1 qualifies
    app.dependency_overrides[get_db] = override_db(kpis=kpis)
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["analyzed_kpis"] == 2


def test_analyzed_fingerprints_reflects_input_count():
    fps = [FakeFingerprint(risk_level="high"), FakeFingerprint(risk_level="low", entity_id="s2")]
    app.dependency_overrides[get_db] = override_db(fingerprints=fps)
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert resp.json()["analyzed_fingerprints"] == 2


def test_insight_ids_are_sequential_starting_at_1():
    """Service assigns ids 1, 2, 3, ... — not DB primary keys."""
    kpis = [FakeKPI("k1", 0.9), FakeKPI("k2", 0.85)]
    app.dependency_overrides[get_db] = override_db(kpis=kpis)
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    ids = [ins["id"] for ins in resp.json()["insights"]]
    assert ids == [1, 2]


def test_insight_id_is_integer():
    app.dependency_overrides[get_db] = override_db(kpis=[FakeKPI(confidence=0.8)])
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    assert isinstance(resp.json()["insights"][0]["id"], int)


def test_insight_ids_are_strictly_sequential():
    """IDs must be exactly [1, 2, 3, ...] — no gaps, no skips, no duplicates."""
    kpis = [
        FakeKPI("avg_logins", 0.9),
        FakeKPI("avg_sessions", 0.85),
        FakeKPI("avg_score", 0.95),
    ]
    app.dependency_overrides[get_db] = override_db(kpis=kpis)
    resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
    ids = [ins["id"] for ins in resp.json()["insights"]]
    assert ids == list(range(1, len(ids) + 1))


def test_generated_count_is_non_negative():
    for kpis, fps in [
        ([], []),
        ([FakeKPI(confidence=0.9)], []),
        ([], [FakeFingerprint(risk_level="high")]),
    ]:
        app.dependency_overrides[get_db] = override_db(kpis=kpis, fingerprints=fps)
        resp = client.post("/insight/generate", json={"entity_id": "s1", "entity_type": "student"})
        assert resp.json()["generated_count"] >= 0
