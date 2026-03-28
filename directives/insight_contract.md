# Directive: Insight Generation Contract

## 1. Purpose

The Insight Generation system synthesizes data from two upstream systems — KPI Discovery and Behavior Fingerprints — and produces human-readable insights and recommendations. It is the first layer of executive intelligence in the Colaberry AI platform.

Each call reads all discovered KPIs and all behavior fingerprints currently in the database, applies rule-based generation logic to identify noteworthy conditions, writes each generated insight to the database, and returns the full result to the caller.

Two types of insights are currently generated:

- **`kpi`** — triggered when a discovered KPI has confidence > 0.7
- **`risk`** — triggered when a behavior fingerprint has `risk_level == "high"`

This system is intended to grow. New insight types should be added to the generator and documented in this directive when implemented.

---

## 2. Endpoint

- **Method:** `POST`
- **Path:** `/insight/generate`
- **Content-Type:** `application/json`
- **Request body:** none required

---

## 3. Inputs

The insight system takes no external inputs from the caller. All data is read internally from the database at call time.

### Internal data sources

| Source table | ORM model | Fields read |
|---|---|---|
| `AI_ChatBot_DiscoveredKPIs` | `DiscoveredKPI` | `kpi_name`, `source_pattern`, `entity_type`, `formula`, `confidence`, `sample_size` |
| `AI_ChatBot_BehaviorFingerprints` | `BehaviorFingerprint` | `entity_type`, `entity_id`, `pattern_name`, `score`, `risk_level` |

### Generation rules (enforced by `InsightGenerator`)

| Trigger condition | Insight type | Title format | Confidence used |
|---|---|---|---|
| KPI `confidence > 0.7` | `"kpi"` | `"High-confidence KPI: {kpi_name}"` | KPI's `confidence` value |
| Fingerprint `risk_level == "high"` | `"risk"` | `"High-risk pattern: {pattern_name}"` | Fingerprint's `score` value |

KPIs and fingerprints that do not meet their trigger condition produce no insight and are silently skipped.

---

## 4. Outputs

### API response (200 OK)

Schema: `InsightGenerateResponse`

| Field | Type | Description |
|---|---|---|
| `generated_count` | int | Number of insights generated in this run |
| `analyzed_kpis` | int | Total KPI rows read from DB |
| `analyzed_fingerprints` | int | Total fingerprint rows read from DB |
| `insights` | list of `InsightResponse` | All generated insights |

Each `InsightResponse`:

| Field | Type | Description |
|---|---|---|
| `id` | int | Sequential position in this run (1-indexed); not the DB primary key |
| `title` | string | Generated insight title |
| `body` | string | Generated insight body text |
| `insight_type` | string | `"kpi"` or `"risk"` |
| `entity_type` | string | Entity category (e.g. `"student"`) |
| `entity_id` | string | Entity identifier (cast to string) |
| `confidence` | float | Confidence score (0.0–1.0) |

Example response:

```json
{
  "generated_count": 1,
  "analyzed_kpis": 1,
  "analyzed_fingerprints": 3,
  "insights": [
    {
      "id": 1,
      "title": "High-confidence KPI: avg_logins",
      "body": "KPI 'avg_logins' has confidence 0.8 for entity type 'student'.",
      "insight_type": "kpi",
      "entity_type": "student",
      "entity_id": "0",
      "confidence": 0.8
    }
  ]
}
```

### DB write

Each generated insight results in one new row in `AI_ChatBot_GeneratedInsights`:

| Column | Source |
|---|---|
| `title` | from `Insight.title` |
| `body` | from `Insight.body` |
| `insight_type` | from `Insight.insight_type` |
| `entity_type` | from `Insight.entity_type` |
| `entity_id` | from `Insight.entity_id` (raw value, not cast) |
| `confidence` | from `Insight.confidence` |
| `source_kpis_json` | not currently populated (column exists for future use) |
| `source_patterns_json` | not currently populated (column exists for future use) |
| `created_at` | DB server default (`GETDATE()`) |

Note: the `id` field in the API response is a sequential counter for the current run only. It does not correspond to the DB primary key of the persisted row.

---

## 5. Rules

- The route (`api/routes/insight.py`) must contain no business logic — only dependency injection, service delegation, and response return.
- All generation logic lives in `core/insight/generator.py` (`InsightGenerator`). It is pure Python with no DB or FastAPI imports.
- DB reads and writes are performed exclusively in `core/insight/service.py` (`InsightService`).
- `core/insight/models.py` defines data structures only (`Insight`, `InsightGenerationResult`). No logic belongs there.
- The generator must be stateless — same KPI and fingerprint input always produces the same insights.
- Every call to `/insight/generate` appends new rows to `AI_ChatBot_GeneratedInsights`. There is no deduplication.
- `entity_id` is stored as-is in the DB but cast to `str` in the API response to satisfy the schema (the `InsightResponse.entity_id` field is typed `str`).
- `GeneratedInsight` is imported inside `save_insights()` at call time (deferred import) to allow the module to load cleanly before the ORM model is registered. This is intentional.
- No secrets, credentials, or environment variables are read inside the insight layer.

---

## 6. Edge Cases

| Condition | Behavior |
|---|---|
| No KPIs in DB and no fingerprints in DB | Generator returns empty insights list; `generated_count=0` |
| All KPIs have `confidence <= 0.7` | No KPI insights generated; fingerprint insights still evaluated |
| No fingerprints have `risk_level == "high"` | No risk insights generated; KPI insights still evaluated |
| KPI missing `kpi_name` key | Title uses `"unknown"` as fallback |
| Fingerprint missing `pattern_name` key | Title uses `"unknown"` as fallback |
| Fingerprint missing `entity_id` key | `entity_id` defaults to `0` |
| DB unavailable (`MSSQL_DATABASE_URL` not set) | `SessionLocal` is `None`; `get_db` raises at request time |
| Multiple runs | Each run appends new rows; historical rows are not deleted |

---

## 7. Verification Requirements

All tests must live under `tests/unit/`.

### Required test cases

| # | Test | Expected |
|---|---|---|
| 1 | Generator with high-confidence KPI (`confidence=0.8`) | One `kpi` insight produced |
| 2 | Generator with low-confidence KPI (`confidence=0.5`) | No insight produced |
| 3 | Generator with high-risk fingerprint (`risk_level="high"`) | One `risk` insight produced |
| 4 | Generator with medium-risk fingerprint (`risk_level="medium"`) | No insight produced |
| 5 | Generator with both qualifying KPI and qualifying fingerprint | Two insights produced |
| 6 | Generator with empty KPI list and empty fingerprint list | `generated_count=0`, `insights=[]` |
| 7 | `InsightGenerationResult` counts match input lengths | `analyzed_kpis` and `analyzed_fingerprints` equal input list lengths |
| 8 | `POST /insight/generate` happy path (mocked DB) | 200, response matches `InsightGenerateResponse` schema |
| 9 | `POST /insight/generate` with empty DB (mocked) | 200, `generated_count=0`, `insights=[]` |

### Test tooling

- `InsightGenerator` tested directly — no DB, no HTTP
- API route tests use FastAPI `TestClient` with mocked `get_db` dependency
- No real DB connections in unit tests
- Tests must be deterministic and runnable with `pytest tests/unit/`

---

## 8. Code Map

| Responsibility | File |
|---|---|
| Data structures | `core/insight/models.py` |
| Generation logic | `core/insight/generator.py` |
| DB load and persistence | `core/insight/service.py` |
| ORM model (write) | `services/models.py` → `GeneratedInsight` |
| ORM model (read — KPIs) | `services/models.py` → `DiscoveredKPI` |
| ORM model (read — fingerprints) | `services/models.py` → `BehaviorFingerprint` |
| Alembic migration | `alembic/versions/0006_add_generated_insights_table.py` |
| API schema | `api/schemas/insight.py` |
| API route | `api/routes/insight.py` |

---

## 9. Definition of Done

- [ ] `InsightGenerator` unit tests exist and pass (all 7 generator cases)
- [ ] API route unit tests exist and pass (mocked DB, cases 8–9)
- [ ] This directive exists at `directives/insight_contract.md`
- [ ] Table `AI_ChatBot_GeneratedInsights` exists in the target database (migration `0006` applied)
- [ ] `POST /insight/generate` returns correct JSON matching `InsightGenerateResponse` schema
- [ ] No secrets introduced in the repository
- [ ] Layer boundaries respected: generator has no DB imports; route has no business logic
- [ ] A junior developer can read this directive and understand the full system
