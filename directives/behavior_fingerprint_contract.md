# Directive: Behavior Fingerprint Contract

## 1. Purpose

The Behavior Fingerprint system evaluates an entity's observed metrics against a named pattern and produces a risk score. It is used to detect behavioral anomalies — for example, identifying students whose engagement metrics match a high-risk disengagement pattern.

The system compares actual metric values to threshold values defined by the caller, computes a score (0.0–1.0) representing how many thresholds were met, assigns a risk level, serializes the result to the database, and returns the persisted record.

This system is read-write. Every call to `/fingerprints/evaluate` writes a new row to `AI_ChatBot_BehaviorFingerprints`.

---

## 2. Endpoint

- **Method:** `POST`
- **Path:** `/fingerprints/evaluate`
- **Content-Type:** `application/json`

---

## 3. Inputs

### JSON Body

| Field | Type | Required | Description |
|---|---|---|---|
| `entity_type` | string | yes | Category of entity being evaluated (e.g. `"student"`, `"cohort"`) |
| `entity_id` | string | yes | Unique identifier of the entity |
| `pattern_name` | string | yes | Name of the behavioral pattern being tested (e.g. `"disengagement"`) |
| `thresholds` | object | yes | Key-value pairs defining the expected metric values or minimums for the pattern |
| `metrics` | object | yes | Key-value pairs of the entity's actual observed metric values |

### Threshold matching rules (enforced by `FingerprintEvaluator`)

- If both threshold and actual value are numeric (`int` or `float`): threshold is met when `actual >= expected`
- If either value is non-numeric: threshold is met when `actual == expected` (exact match)
- Score = `matched_thresholds / total_thresholds` (0.0 if no thresholds defined)

### Risk level assignment

| Score range | Risk level |
|---|---|
| `>= 0.8` | `"high"` |
| `>= 0.5` | `"medium"` |
| `< 0.5` | `"low"` |

---

## 4. Outputs

### Response (200 OK)

| Field | Type | Description |
|---|---|---|
| `id` | int | Auto-generated primary key of the persisted row |
| `entity_type` | string | Echoed from request |
| `entity_id` | string | Echoed from request |
| `pattern_name` | string | Echoed from request |
| `score` | float | Computed score (0.0–1.0) |
| `risk_level` | string | `"low"`, `"medium"`, or `"high"` |
| `details_json` | string | JSON string containing `matched`, `total`, and `metrics` |

### DB write

Every successful call inserts one row into `AI_ChatBot_BehaviorFingerprints`:

| Column | Source |
|---|---|
| `entity_type` | from request |
| `entity_id` | from request |
| `pattern_name` | from request |
| `score` | computed by evaluator |
| `risk_level` | computed by evaluator |
| `details_json` | JSON-serialized evaluator details dict |
| `created_at` | DB server default (`GETDATE()`) |

---

## 5. Rules

- The route (`api/routes/fingerprint.py`) must contain no business logic — only request parsing, service delegation, and response construction.
- All scoring logic lives in `core/fingerprint/evaluator.py` (`FingerprintEvaluator`). It is pure Python with no DB or FastAPI imports.
- All DB writes are performed by `core/fingerprint/service.py` (`FingerprintService`). It receives a SQLAlchemy session from the FastAPI `get_db` dependency.
- `core/fingerprint/patterns.py` defines data structures only (`BehaviorPattern`, `FingerprintResult`). No logic belongs there.
- The evaluator must be stateless and idempotent — same inputs always produce the same score and risk level.
- No secrets, credentials, or environment variables are read inside the fingerprint layer.
- Every call creates a new row. There is no deduplication or upsert logic.

---

## 6. Edge Cases

| Condition | Behavior |
|---|---|
| `thresholds` is an empty dict | Score = 0.0, risk_level = `"low"` |
| `metrics` contains keys not in `thresholds` | Extra keys are ignored |
| `thresholds` contains keys not in `metrics` | Missing metric treated as `None`; numeric threshold not met, non-numeric not met |
| `entity_id` refers to a non-existent entity | No validation — row is written regardless |
| DB unavailable (`MSSQL_DATABASE_URL` not set) | `SessionLocal` is `None`; `get_db` will raise at request time |

---

## 7. Verification Requirements

All tests must live under `tests/unit/`.

### Required test cases

| # | Test | Expected |
|---|---|---|
| 1 | All thresholds met (numeric) | score = 1.0, risk_level = `"high"` |
| 2 | No thresholds met | score = 0.0, risk_level = `"low"` |
| 3 | Partial match (50–79%) | risk_level = `"medium"` |
| 4 | Empty thresholds dict | score = 0.0, risk_level = `"low"` |
| 5 | Non-numeric threshold — exact match | threshold counted as met |
| 6 | Non-numeric threshold — no match | threshold counted as not met |
| 7 | `POST /fingerprints/evaluate` happy path (mocked DB) | 200, response fields match schema |
| 8 | `POST /fingerprints/evaluate` missing required field | 422 |

### Test tooling

- Use `pytest` with `FingerprintEvaluator` tested directly (no DB, no HTTP)
- API route tests use FastAPI `TestClient` with mocked `get_db` dependency
- No real DB connections in unit tests
- Tests must be deterministic and runnable with `pytest tests/unit/`

---

## 8. Code Map

| Responsibility | File |
|---|---|
| Data structures | `core/fingerprint/patterns.py` |
| Scoring logic | `core/fingerprint/evaluator.py` |
| DB persistence | `core/fingerprint/service.py` |
| ORM model | `services/models.py` → `BehaviorFingerprint` |
| Alembic migration | `alembic/versions/0004_add_behavior_fingerprint_table.py` |
| API schema | `api/schemas/fingerprint.py` |
| API route | `api/routes/fingerprint.py` |

---

## 9. Definition of Done

- [ ] `FingerprintEvaluator` unit tests exist and pass
- [ ] API route unit tests exist and pass (mocked DB)
- [ ] This directive exists at `directives/behavior_fingerprint_contract.md`
- [ ] Table `AI_ChatBot_BehaviorFingerprints` exists in the target database
- [ ] No secrets introduced in the repository
- [ ] Layer boundaries respected: evaluator has no DB imports; route has no business logic
- [ ] A junior developer can read this directive and understand the full system
