# Directive: KPI Discovery Contract

## 1. Purpose

The KPI Discovery system automatically derives measurable performance indicators from existing behavior fingerprint data. Rather than requiring a human to define KPIs manually, this system reads the stored fingerprint records, applies analysis logic, and surfaces computed metrics that can be tracked over time.

The primary use case is identifying aggregate patterns across a population of entities (e.g. students) — for example, computing average login frequency across all fingerprinted students. Discovered KPIs are written to the database and returned to the caller.

Every call to `POST /kpi/discover` is a full discovery run: it reads all current fingerprints, re-computes KPIs from scratch, and writes new rows. There is no deduplication or upsert — each run appends new `DiscoveredKPI` rows.

---

## 2. Endpoint

- **Method:** `POST`
- **Path:** `/kpi/discover`
- **Content-Type:** `application/json`
- **Request body:** none required

---

## 3. Inputs

The discovery system takes no external inputs from the caller. All data is read internally from the database.

### Internal data source

| Source table | ORM model | Fields used |
|---|---|---|
| `AI_ChatBot_BehaviorFingerprints` | `BehaviorFingerprint` | `entity_type`, `entity_id`, `pattern_name` |

### Current analyzer behavior (`KPIDiscoveryAnalyzer`)

The analyzer receives a list of fingerprint dicts and computes the following:

| KPI name | Formula | Entity type | Source pattern | Confidence |
|---|---|---|---|---|
| `avg_logins` | `avg(logins)` | `student` | `auto` | `0.8` |

The `logins` value is read from each fingerprint's `metrics.logins` key. If absent, it defaults to `0`.

This list of derived KPIs is expected to grow as the analyzer is extended. New KPIs must be added to this directive when implemented.

---

## 4. Outputs

### API response (200 OK)

| Field | Type | Description |
|---|---|---|
| `kpis_found` | int | Count of distinct KPIs discovered in this run |
| `kpis` | list of string | Names of all discovered KPIs |

Example:

```json
{
  "kpis_found": 1,
  "kpis": ["avg_logins"]
}
```

### DB write

Each discovered KPI results in one new row in `AI_ChatBot_DiscoveredKPIs`:

| Column | Source |
|---|---|
| `kpi_name` | from `DiscoveredKPI.kpi_name` |
| `source_pattern` | from `DiscoveredKPI.source_pattern` |
| `entity_type` | from `DiscoveredKPI.entity_type` |
| `formula` | from `DiscoveredKPI.formula` |
| `confidence` | from `DiscoveredKPI.confidence` |
| `sample_size` | number of fingerprint rows analyzed |
| `discovered_at` | DB server default (`GETDATE()`) |

### Edge case — no fingerprints in DB

If `AI_ChatBot_BehaviorFingerprints` contains zero rows, the analyzer returns an empty result:

```json
{
  "kpis_found": 0,
  "kpis": []
}
```

No rows are written to `AI_ChatBot_DiscoveredKPIs`.

---

## 5. Rules

- The route (`api/routes/kpi.py`) must contain no business logic — only dependency injection, service delegation, and response construction.
- All analysis logic lives in `core/kpi_discovery/analyzer.py` (`KPIDiscoveryAnalyzer`). It is pure Python with no DB or FastAPI imports.
- DB reads and writes are performed exclusively in `core/kpi_discovery/service.py` (`KPIDiscoveryService`).
- `core/kpi_discovery/models.py` defines data structures only (`DiscoveredKPI`, `KPIDiscoveryResult`). No logic belongs there.
- The analyzer must be stateless — same fingerprint input always produces the same KPI output.
- Each discovery run appends new rows. There is no deduplication, merging, or deletion of prior runs.
- `KPIDiscoveryService.save_kpis()` must iterate `kpis.values()` — never bare `kpis` dict iteration (iterating keys causes `AttributeError`).
- No secrets, credentials, or environment variables are read inside the KPI discovery layer.

---

## 6. Edge Cases

| Condition | Behavior |
|---|---|
| No fingerprints in DB | Analyzer returns empty `kpis={}`, `analyzed_count=0`; no rows written |
| Fingerprint row has no `metrics` key | `logins` defaults to `0` via `.get("metrics", {}).get("logins", 0)` |
| Fingerprint row has `metrics` but no `logins` | Same as above — defaults to `0` |
| DB unavailable (`MSSQL_DATABASE_URL` not set) | `SessionLocal` is `None`; `get_db` raises at request time |
| Multiple discovery runs | Each run appends new rows; historical rows are not deleted or updated |

---

## 7. Verification Requirements

All tests must live under `tests/unit/`.

### Required test cases

| # | Test | Expected |
|---|---|---|
| 1 | Analyzer with non-empty fingerprint list | Returns `KPIDiscoveryResult` with `avg_logins` KPI |
| 2 | Analyzer with empty fingerprint list | Returns `kpis={}`, `analyzed_count=0`, `metadata={}` |
| 3 | Analyzer `avg_logins` value is correct average | `metadata["avg_logins"]` == mean of all `logins` values |
| 4 | Analyzer with fingerprints missing `logins` key | `logins` defaults to `0`, no exception raised |
| 5 | `save_kpis` iterates `kpis.values()` not `kpis` | DB rows created correctly; no `AttributeError` |
| 6 | `POST /kpi/discover` happy path (mocked DB) | 200, `kpis_found >= 0`, `kpis` is a list of strings |
| 7 | `POST /kpi/discover` with empty fingerprint table (mocked) | 200, `kpis_found=0`, `kpis=[]` |

### Test tooling

- `KPIDiscoveryAnalyzer` tested directly — no DB, no HTTP
- API route tests use FastAPI `TestClient` with mocked `get_db` dependency
- No real DB connections in unit tests
- Tests must be deterministic and runnable with `pytest tests/unit/`

---

## 8. Code Map

| Responsibility | File |
|---|---|
| Data structures | `core/kpi_discovery/models.py` |
| Analysis logic | `core/kpi_discovery/analyzer.py` |
| DB load and persistence | `core/kpi_discovery/service.py` |
| ORM model (write) | `services/models.py` → `DiscoveredKPI` |
| ORM model (read) | `services/models.py` → `BehaviorFingerprint` |
| Alembic migration | `alembic/versions/0005_add_discovered_kpis_table.py` |
| API route | `api/routes/kpi.py` |

---

## 9. Definition of Done

- [ ] `KPIDiscoveryAnalyzer` unit tests exist and pass
- [ ] API route unit tests exist and pass (mocked DB)
- [ ] This directive exists at `directives/kpi_discovery_contract.md`
- [ ] Table `AI_ChatBot_DiscoveredKPIs` exists in the target database
- [ ] `POST /kpi/discover` returns correct JSON with `kpis_found` and `kpis` fields
- [ ] No secrets introduced in the repository
- [ ] Layer boundaries respected: analyzer has no DB imports; route has no business logic
- [ ] A junior developer can read this directive and understand the full system
