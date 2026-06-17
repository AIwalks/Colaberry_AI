# PROGRESS.md
**Colaberry Sentinel OS — Session Log & System Hardening Tracker**

Last updated: 2026-06-17 (Sprint 8 completion hardening: governance_gate_contract.md gap analysis resolved (4 fixes), 3 additional wiring tests added to TestGovernanceGateWiring (7→10), targeted Sprint 8 run 81 passed 1 skipped — fully validated and ready for commit)

---

## Governance

> **Note:** `PROGRESS.md` was initially created before `CLAUDE.md` verification — corrected after enforcement reset on 2026-04-21.

- [x] `CLAUDE.md` exists at repo root — confirmed by direct Read on 2026-04-21 after enforcement reset
- [x] `CLAUDE.md` rules read in full and explicitly agreed to — confirmed 2026-04-21
- [x] `PROGRESS.md` exists at repo root
- [ ] Project state summarized and validated against current codebase (not yet done under correct protocol)
- [ ] First actionable task identified and approved by user

---

## Completed Work

> **Note:** Items below were carried from prior session memory and reflect changes made before the enforcement reset. They have not been re-verified under the current session's correct protocol. Each item should be confirmed before being treated as done.

### Infrastructure & Safety
- [x] Replace dead `SessionLocal is None` guard with `MSSQL_CONFIGURED` in `trigger_worker.py`
- [x] Add per-trigger `try/except` isolation in worker loop — failures continue, not crash
- [x] Fix service factory in `app/main.py` — `DbTriggerProcessingService` now runs locally
- [x] Add `MSSQL_CONFIGURED` safety guard in `execution/init_local_db.py` — prevents running against production
- [x] Remove `local.db` from git tracking; add to `.gitignore`

### API & Auth
- [x] Add API key authentication layer (`config/auth.py`) with `require_api_key` dependency
- [x] Apply `Depends(require_api_key)` to all FastAPI routes in `app/main.py`

### Outbound Delivery
- [x] Rewrite `send_text()` to return `list[dict]` (DeliveryResult) instead of `bool`
- [x] Implement DeliveryResult shape: `{success, channel, provider, provider_id, error, recipient}`
- [x] Add provider adapter stubs: `_send_twilio_sms`, `_send_twilio_whatsapp`, `_send_twilio_voice`, `_send_mandrill_email`
- [x] Forward `cbm_id` into all `DeliveryLog` inserts
- [x] Fix commit-before-send ordering in `process_trigger()` to prevent double-send

### Delivery Truth Propagation
- [x] Capture `delivery_results` from `send_text()` in `process_trigger()`
- [x] Compute `sent = any(r.get("success") for r in delivery_results)` — no more unconditional `True`

### Schema
- [x] Remove `explanation` and `recommended_action` from `InsightResponse` — aligned with directive

### Directives
- [x] Rewrite `directives/outbound_delivery_contract.md` — new signature, DeliveryResult structure, rules
- [x] Create `directives/database_safety.md` — init_local_db safety guard documented
- [x] Create `docs/OWNER_CONTROL_PLANE.md` — governance template (8 sections)

### Delivery Outcome Tracking (DeliverySucceeded)
- [x] Add nullable `Boolean` column `DeliverySucceeded` to `TriggeredUser` ORM model (`services/models.py`)
- [x] Add Alembic migration `0007_add_delivery_succeeded_to_triggered_users.py` — `op.add_column` + `op.drop_column` downgrade; chains from `0006`
- [x] Write `DeliverySucceeded` back to `TriggeredUser` after `send_text()` returns in `process_trigger()` (`services/mentor_message_service.py`)
- [x] Fix correctness gap: exception path (`send_text()` raises) now writes `False` before returning, not `NULL`
- [x] Fix semantic regression: retry path uses `delivery_succeeded` (the computed intended value), not hardcoded `False` — preserves `NULL` for no-attempt cases
- [x] Add single retry with fresh session on write-back failure; `[CRITICAL]` log if retry also fails
- [x] Add local SQLite schema update (`ALTER TABLE`) — local `local.db` column now matches ORM model

  > Verified: schema change implemented; exception + retry + NULL semantics correct; deterministic 3-state test coverage added; full suite 243 passed, 6 skipped, 0 failures.

### Tests
- [x] `tests/unit/test_trigger_worker.py` — new: verifies per-trigger isolation on failure
- [x] `tests/unit/test_trigger_process_contract.py` — updated: factory routing, local DB insertion
- [x] `tests/unit/test_outbound_delivery_service.py` — updated: all assertions reflect `list[dict]` return type; added `TestDeliveryContract` (2 tests)
- [x] `tests/unit/test_mentor_message_trigger.py` — added `TestDeliverySucceededWriteback` (5 tests): True / False / NULL / exception / retry-semantics; all pass against local SQLite

---

## Sprint 2 — Governed AI Insight Generation with Explainability
**Committed: 2026-05-13 | Commit: d22c8f6**
**Status: Tested**

### What Changed
- **New:** `services/ai_insight_service.py` — `generate_ai_insight()` wraps Claude API call; returns structured JSON with `summary`, `risk_level`, `confidence`, `recommended_action`, `explainability`; falls back gracefully on API failure
- **New:** `api/routes/insight.py` — insight generation endpoint with request/response validation
- **Modified:** `api/schemas/insight.py` — schema aligned with new AI response shape
- **Modified:** `app/main.py` — insight router registered
- **New:** Alembic migrations:
  - `0008_add_thread_id_to_engagement_events.py` — adds `thread_id` column to EngagementEvents for conversation continuity
  - `0009_add_student_responses_table.py` — new StudentResponses table
- **New:** `docs/AI_INSIGHT_LAYER.md`, `docs/AI_ROUTE_VALIDATION.md` — architecture documentation
- **Modified:** `frontend/src/App.tsx` — routing updated for insight views

### Validation
- Tests added: `tests/unit/test_ai_insight_route.py` (route contract), `tests/unit/test_ai_insight_service.py` (service unit), `tests/unit/test_thread_id_persistence.py` (schema migration)
- All tests pass at commit time

### Risks / Limitations
- Claude API call is live; no mock mode toggle for local dev
- `tmp/staging_claim_test.py` committed — should be removed from permanent history (tmp/ should never be committed)
- Migrations 0008/0009 require `alembic upgrade head` against target DB before going live

### Maturity
- `ai_insight_service.py` — **Tested**
- `insight` route — **Tested**
- Migrations 0008/0009 — **Integrated** (not yet applied to any verified DB)

---

## Sprint 3 — Governed AI Interpretation and Review Workflow (Sentinel OS)
**Committed: 2026-05-20 | Commit: db7e075**
**Status: Tested (backend); Scaffolded (frontend)**

### What Changed
**New services:**
- `services/sentinel_extraction_service.py` (~958 lines) — reads TriggerData, TriggeredUsers, AuditLog, EngagementEvents; builds structured extraction with `dimensions`, `kpis`, `fingerprints`; mock mode for local dev
- `services/sentinel_orchestration_service.py` (~591 lines) — full pipeline: extract → evaluate → load/invalidate interpretation → call AI → write back; governed reuse of existing interpretations
- `services/governance_review_service.py` (~322 lines) — human review queue for AI interpretations; approve/reject/override workflow
- `services/material_change_evaluation_service.py` (~373 lines) — determines whether KPI delta warrants a new AI interpretation vs. reusing the existing one
- `services/database_connection_validator.py` (~187 lines) — connection health check utility

**New API:**
- `api/routes/sentinel.py` (~445 lines) — sentinel endpoints: interpretations, governance queue, reuse metrics, risk evolution, student detail
- `api/schemas/ai_interpretation.py`, `api/schemas/governance_review.py` — Pydantic schemas

**New DB models and migrations:**
- `services/models.py` — new ORM models: `AIInterpretation`, `GovernanceReview`, `BehaviorFingerprint`
- `0010_add_ai_interpretations_table.py` — AI interpretations table (103 lines)
- `0011_add_governance_reviews_table.py` — governance reviews table (91 lines)

**New frontend:**
- `frontend/src/pages/SentinelDashboard.tsx` (~249 lines) — top-level dashboard page
- New components: `EmptyState`, `GovernanceQueue`, `InterpretationTimeline`, `ReuseMetrics`, `RiskEvolution`, `StatusBadge`, `StudentDetailView`
- New hooks: `useSentinelData.ts` additions
- New types: `frontend/src/types/sentinel.ts`
- Component tests: `EmptyState.test.tsx`, `GovernanceQueue.test.tsx`, `StatusBadge.test.tsx`, `SentinelDashboard.test.tsx`

### Validation
- Tests added (all backend):
  - `test_ai_interpretation_model.py` (~402 lines)
  - `test_database_connection_validator.py` (~324 lines)
  - `test_governance_review_service.py` (~718 lines)
  - `test_material_change_evaluation_service.py` (~742 lines)
  - `test_sentinel_extraction_service.py` (~801 lines)
  - `test_sentinel_orchestration_service.py` (~789 lines)
- Frontend component tests: 3 files
- Backend tests pass at commit time; frontend tests depend on vitest setup

### Risks / Limitations
- Frontend dashboard not browser-tested — component tests verify rendering only
- Migrations 0010/0011 need `alembic upgrade head` against target DB
- `SENTINEL_LIVE=False` (mock mode) is the default; real DB extraction unverified outside mock
- `app/main.py` and `config/database.py` modified — regression risk to existing delivery pipeline

### Maturity
- `SentinelExtractionService` — **Tested**
- `SentinelOrchestrationService` — **Tested**
- `GovernanceReviewService` — **Tested**
- `MaterialChangeEvaluationService` — **Tested**
- `DatabaseConnectionValidator` — **Tested**
- `AIInterpretation` / `GovernanceReview` models — **Tested**
- Sentinel API routes — **Partially Implemented** (route contract exists; real DB path untested)
- Frontend SentinelDashboard — **Scaffolded** (components render; no browser/E2E test)
- Migrations 0010/0011 — **Integrated** (files exist, not applied to verified DB)

---

## Sprint 4 — KPI Interpretation Layer + Fingerprint Wiring
**Date: 2026-05-28 | Status: READY FOR COMMIT — 2026-06-03**
**Status: Tested (unit); Partially Implemented (wiring)**

### What Changed (uncommitted)

**`core/insight/generator.py`** — Added `interpret_kpi(kpi_name, value, unit)`:
- Deterministic, value-aware KPI severity rules — no LLM, no randomness
- Returns `{severity, suppress, title, body, recommended_action}`
- `suppress=True` → healthy signal; caller skips generating an insight
- Maps 8 KPI types: `attendance_percentage`, `last_activity_days`, `last_login_days`, `homeworks_behind`, `avg_hw_score`, `submission_rate` / `assignment_submission_rate`, `trigger_completion_rate`, `intervention_completion_rate`
- Unknown KPI names fall through to existing generic behaviour (non-breaking)
- `InsightGenerator.generate_insights()` updated to call `interpret_kpi` per KPI; healthy KPIs suppressed cleanly

**`services/fingerprint_generator_service.py`** (new, untracked):
- `FingerprintGeneratorService` — evaluates 4 deterministic behavioral rules against extracted signals
- Rules: `stale_login_pattern` (≥14 days), `stale_activity_pattern` (≥14 days), `low_trigger_completion` (<25% rate with ≥3 triggers), `active_but_disconnected` (active class + active status + ≥14 days inactivity)
- 24-hour dedup guard against `BehaviorFingerprint` table — prevents duplicate writes
- Writes ONLY to `AI_ChatBot_BehaviorFingerprints`; no reads/writes to core production tables
- Error isolation: per-fingerprint try/except; DB rollback on failure; returns partial results

**`services/sentinel_orchestration_service.py`** — `FingerprintGeneratorService` wired as Step 1b:
- Runs immediately after extraction (before AI call)
- New fingerprints appended to `current_fingerprints` so AI sees them
- Non-fatal: fingerprint failure is logged and execution continues
- Debug payload logging added before AI call (KPIs + fingerprints JSON dump)

**`services/ai_insight_service.py`** — System prompt and KPI label map overhauled:
- Prompt rewritten for advisor-readable language (no jargon: no "behavioral fingerprint", "KPI", "sentinel", "trigger completion", "material change", "entity")
- `_KPI_LABEL_MAP` added — translates internal signal names to plain English for AI context
- Confidence calibration guidance added for sparse data

**`api/routes/sentinel.py`** — `POST /sentinel/evaluate` endpoint added:
- Runs full `SentinelOrchestrationService` pipeline for one student/dimension
- Request model: `{entity_id, entity_type, dimension}`
- Returns orchestration result as JSON

**`api/schemas/insight.py`** — minor schema additions

**Other modified files** (test and frontend updates):
- `core/insight/service.py`, `skills/insight_explainer/skill.py`
- `frontend/src/App.tsx`, `frontend/src/hooks/useSentinelData.ts`, `frontend/src/pages/SentinelDashboard.tsx`, `frontend/src/types/sentinel.ts`
- `tests/e2e/test_insight_flow.py`, `tests/unit/test_insight_generator.py`, `tests/unit/test_sentinel_extraction_service.py`

**New untracked test files:**
- `tests/unit/test_fingerprint_generator_service.py` — 10 test classes covering rule evaluation (all 4 rules), dedup, DB write, partial failure, error isolation
- `tests/unit/test_interpret_kpi.py` — 9 test classes covering all 8 KPI interpreters, boundary values (fence-post), fallback for unknown/None/non-numeric values, integration smoke-test through `InsightGenerator`

### Validation
- `test_fingerprint_generator_service.py` — **46 passed, 0 failed** (run 2026-06-03; 10 classes: signal flattening, all 4 behavioral rules, multi-rule firing, dedup, DB write, partial failure, error isolation)
- `test_interpret_kpi.py` — **81 passed, 0 failed** (run 2026-06-03; 9 classes: all 8 KPI interpreters, boundary/fence-post values, non-numeric fallback, alias handling, integration smoke-test through `InsightGenerator`)
- `test_insight_generator.py` — updated to reflect `interpret_kpi` integration
- **Sprint 4 test gate total: 127 passed, 0 failed** (1.23 s — 2026-06-03)

### Risks / Limitations
- All Sprint 4 changes are UNCOMMITTED — need clean commit before they are part of repo history
- ~~`POST /sentinel/evaluate` has no auth guard in current diff~~ — **RESOLVED 2026-06-03**: confirmed protected at router level via `app.include_router(sentinel_router, dependencies=[Depends(require_api_key)])` in `app/main.py:106`; all sentinel routes inherit the dependency; no per-route change required
- ~~Debug payload logging in orchestration writes full KPI + fingerprint JSON to logs — may be noisy in production~~ — **RESOLVED 2026-06-03**: all 9 `SENTINEL_DEBUG_PAYLOAD` `logger.info()` calls changed to `logger.debug()` in `sentinel_orchestration_service.py`; payload is silent at production INFO level
- ~~`interpret_kpi` thresholds are hardcoded — no directive documents them yet; risk of threshold drift~~ — **RESOLVED 2026-06-03**: `directives/kpi_interpretation_contract.md` created (279 lines); all 8 KPI rules documented with exact thresholds, business rationale, suppress=True contract, and mandatory threshold-change process

### Maturity
- `interpret_kpi()` — **Tested** (uncommitted; 127 unit tests passing as of 2026-06-03)
- `FingerprintGeneratorService` — **Tested** (uncommitted)
- Fingerprint wiring in orchestration — **Partially Implemented** (uncommitted; mock-mode untested end-to-end)
- `POST /sentinel/evaluate` — **Scaffolded** (uncommitted; auth guard confirmed — router-level `Depends(require_api_key)` in `app/main.py:106`)
- AI prompt overhaul — **Partially Implemented** (uncommitted; no before/after comparison test)
- `directives/kpi_interpretation_contract.md` — **Integrated** (279 lines; 10 sections; all 8 KPI rules with thresholds, business rationale, suppress=True contract, and threshold-change process)

---

## Sprint 5 — Outcome Learning: Full Implementation
**Date: 2026-05-29 | Status: READY FOR COMBINED SPRINT 5+6 COMMIT — 2026-06-04**
**Status: Tested (unit + local); E2E pending DB validation**

All implementation steps complete. Unit tests passing locally. E2E tests skip without
`MSSQL_DATABASE_URL` and are ready to run once migration 0012 is applied to SQL Server.

### What Changed (uncommitted)

**`services/models.py`** — `InterventionOutcome` ORM model added (model #14):
- `__tablename__ = "AI_ChatBot_InterventionOutcomes"`
- `__table_args__`: composite index `ix_intervention_outcomes_outcome_window_end` on `(outcome, window_end)` — required for scheduler query `WHERE outcome = 'pending' AND window_end <= NOW()`
- 20 columns: id, created/updated_at, cbm_id (UNIQUE), user_id, interpretation_id, window_start/end, evaluation_window_days, delivery_gate_passed, before_last_activity_days, before_risk_level, before_snapshot_source, after_last_activity_days, after_risk_level, after_captured_at, outcome, outcome_reason, eligible_for_learning, evaluated_at
- No FK constraints — consistent with DeliveryLog and GovernanceReview patterns

**`alembic/versions/0012_add_intervention_outcomes_table.py`** (new):
- revision="0012", down_revision="0011"
- Creates `AI_ChatBot_InterventionOutcomes` with all 20 columns and server defaults
- Server defaults: `evaluation_window_days=14`, `delivery_gate_passed=FALSE`, `before_snapshot_source='unavailable'`, `outcome='pending'`
- Creates 5 indexes: `uq_intervention_outcomes_cbm_id` (UNIQUE), `ix_..._user_id`, `ix_..._interpretation_id`, `ix_..._eligible_for_learning`, `ix_..._outcome_window_end` (composite)
- `downgrade()` drops all indexes before dropping table

**`services/intervention_outcome_service.py`** (new, ~515 lines):
- `InterventionOutcomeService` — manages enrollment + evaluation lifecycle
- `enroll(db, cbm_id, user_id, delivery_succeeded, window_start, evaluation_window_days=14)`:
  - Idempotent: dedup via `cbm_id` UNIQUE; returns existing record without modification
  - `delivery_succeeded is True` → gate_passed; `None` or `False` → gate not passed
  - Three-tier before-state: `AIInterpretation.source_snapshot_json` → `TriggerData.LastActivityDays` → `'unavailable'`
  - Non-fatal: full try/except; rollback on error; returns None on failure
- `evaluate_ready_outcomes(db, minimum_delta_days=3) → int`:
  - Queries `outcome='pending' AND window_end <= utcnow()`; evaluates each with per-record exception isolation
- `_evaluate_one`: 4 inconclusive checks in priority order (delivery gate → before state None → student already healthy ≤3 days → after state unavailable), then improved/not_improved via `delta = before - after`
- `_extract_activity_days_from_snapshot`: handles Shape A (`kpis[].kpi_name`) and Shape B (`dimensions.*.signals[].name`)

**`services/mentor_message_service.py`** — enrollment wired as non-blocking side effect:
- `from services.intervention_outcome_service import InterventionOutcomeService` added to imports
- `window_start = triggered.InsertDate` captured inside the main session block alongside `user_id`
- `InterventionOutcomeService().enroll()` called in **both** delivery paths:
  - Happy path: after `DeliverySucceeded` write-back, before final return; passes computed `delivery_succeeded`
  - Exception path: after `DeliverySucceeded=False` write-back, before `return {"reason": "delivery_failed"}`; passes hardcoded `False`
- Both call sites wrapped in `try/except Exception` — enroll failure is logged and swallowed; `process_trigger()` return value unchanged
- `already_claimed` early-return is unaffected — both call sites are below it; enroll fires exactly once per trigger

**`services/worker/outcome_evaluation_worker.py`** (new):
- `evaluate_pending_outcomes() → int`: short-circuits if `not MSSQL_CONFIGURED`; opens one session; delegates entirely to `InterventionOutcomeService.evaluate_ready_outcomes(session)`; returns count
- Runnable as `python -m services.worker.outcome_evaluation_worker`

**`services/worker/run_outcome_evaluation_worker.py`** (new):
- Long-running poll loop; default interval 300 s (`_POLL_INTERVAL_SECONDS`)
- Rationale: outcomes only become evaluable after a 14-day window — 5-minute polling is more than sufficient
- Graceful Ctrl+C shutdown

### Validation

| File | Tests | Result |
|---|---|---|
| `tests/unit/test_intervention_outcome_service.py` | 66 (10 classes) | **66 passed** (re-confirmed 2026-06-04 post-Sprint-4-commit) |
| `tests/unit/test_mentor_message_trigger.py` | 14 total | **13 passed, 1 skipped** (MSSQL integration test; expected; Sprint 6 class also present — file is mixed) |
| `tests/unit/test_outcome_evaluation_worker.py` | 6 | **6 passed** (re-confirmed 2026-06-04 post-Sprint-4-commit) |
| `tests/e2e/test_outcome_learning_flow.py` | 11 | **11 skipped** — `MSSQL_DATABASE_URL` not set locally |
| **Sprint 5 unit gate total** | **72** | **72 passed, 0 failed** (1.07 s — 2026-06-04) |

`test_intervention_outcome_service.py` classes: `TestEnrollmentHappyPath` (9), `TestEnrollmentDeliveryGate` (3), `TestDuplicatePrevention` (3), `TestBeforeStateResolution` (8), `TestSnapshotParsing` (9), `TestImprovedOutcome` (7), `TestNotImprovedOutcome` (6), `TestInconclusiveOutcomes` (10), `TestEvaluateReadyOutcomes` (4), `TestDefensiveness` (7).

`test_mentor_message_trigger.py` additions: `TestOutcomeEnrollmentTriggered` (4 tests) — enroll called after successful delivery, enroll called after failed delivery, enroll failure absorbed, `already_claimed` path skips enroll.

`test_outcome_evaluation_worker.py`: guard short-circuits without MSSQL, session not opened when guard fires, `evaluate_ready_outcomes` called with session, count propagated, zero-record case, exception behavior documented.

`test_outcome_learning_flow.py` E2E scenarios: enrollment creates pending record, idempotent enrollment, inconclusive (delivery gate), inconclusive (no before-state), inconclusive (healthy student), not_improved (delta=0), improved (delta=10), evaluated_at timestamped correctly, eligible_for_learning=False for all inconclusive variants, eligible_for_learning=True for scored outcomes, cleanup meta-test.

### Risks / Limitations
- All Sprint 5 changes are UNCOMMITTED — commit strategy decision required (see below)
- **Mixed-file blocker**: `services/models.py`, `services/mentor_message_service.py`, and `tests/unit/test_mentor_message_trigger.py` contain Sprint 5 AND Sprint 6 changes interleaved — cannot be staged for Sprint 5 alone without `git add -p` partial staging or combining Sprint 5+6 into one commit. Recommended: combine Sprint 5 and Sprint 6 into a single commit.
- ~~No directive for `InterventionOutcomeService`~~ — **RESOLVED 2026-06-04**: `directives/intervention_outcome_contract.md` created (466 lines); all 4 inconclusive checks, `eligible_for_learning` semantics, before-state priority, snapshot shapes, and threshold-change process documented
- Migration 0012 not yet applied to SQL Server — `AI_ChatBot_InterventionOutcomes` table does not exist in any live DB yet; E2E tests cannot run until `alembic upgrade head` is executed
- `eligible_for_learning` semantics: `True` = labeled training example (improved/not_improved); `False` = inconclusive; `NULL` = pending
- `TriggerData` E2E helper inserts a sentinel row (`UserID=8888888`) — if the real SQL Server table has additional `NOT NULL` columns beyond `UserID`, `UserName`, `FirstName`, `LastName`, the insert will fail and `_insert_trigger_data()` will need those columns added

### Maturity
- `InterventionOutcome` ORM model — **Tested**
- Migration 0012 — **Integrated** (file exists; not yet applied to any DB)
- `InterventionOutcomeService` — **Tested** (72 unit tests passing as of 2026-06-04)
- Enrollment wiring (`mentor_message_service.py`) — **Tested**
- Evaluation worker (`outcome_evaluation_worker.py`) — **Tested**
- E2E flow (`test_outcome_learning_flow.py`) — **Integrated** (tests written; skipping locally; DB validation pending)
- `directives/intervention_outcome_contract.md` — **Integrated** (466 lines; 13 sections; 4 inconclusive checks, eligible_for_learning semantics, before-state priority, snapshot parsing, threshold-change process)

---

## Sprint 5 — E2E Test Fixture Fixes (SQL Server Validation)
**Date: 2026-05-30 | Status: UNCOMMITTED — included in Sprint 5 commit package**

### What Changed

**`tests/e2e/test_outcome_learning_flow.py`** — three fixture fixes, no application code touched:

1. **IDENTITY_INSERT failure** — replaced ORM-based `_insert_trigger_data()` with a raw `session.execute(text(...))` INSERT to avoid SQLAlchemy MSSQL dialect automatically issuing `SET IDENTITY_INSERT ON` for `TriggerData.UserID`. Root cause: `mapped_column(Integer, primary_key=True)` defaults to `autoincrement='auto'`; the dialect's `pre_exec()` hook fires when an explicit PK value is supplied. The real SQL Server column has no IDENTITY property.

2. **`evaluated_at` precision failure** — updated assertion from strict `>=` to `>= before_eval - timedelta(milliseconds=10)`. Root cause: SQL Server `DATETIME` rounds to ~3.33 ms precision; `datetime.utcnow()` has microsecond precision; the stored value can round below the Python capture point.

3. **NOT NULL columns** — added `GroupStatus`, `ChatGPT_prompt`, `DataDictionary` to the raw SQL INSERT. Root cause: real SQL Server schema has additional NOT NULL columns not present in the ORM model; omitting them causes `Cannot insert NULL into column` failures.

### Validation
- E2E tests are ready to re-run against SQL Server; all fixture errors corrected
- No application code, ORM models, or migrations were modified

### Maturity
- `test_outcome_learning_flow.py` — **Integrated** (fixture corrected; DB validation run required)

---

## Sprint 6 — Recommendation Learning (Phase 1–5)
**Date: 2026-05-30 | Status: READY FOR COMBINED SPRINT 5+6 COMMIT — 2026-06-04**
**Status: Tested (unit gate: 61 passed, 0 failed — re-confirmed 2026-06-04 post-Sprint-4-commit)**

### What Changed

**`alembic/versions/0013_add_recommendations_table.py`** (new):
- revision="0013", down_revision="0012"
- Creates `AI_ChatBot_Recommendations` with 18 columns
- Notable: `recommendation_key` (granular learning identifier, separate from `recommendation_type`), `recommendation_context_json` NOT NULL (frozen student state snapshot at generation time), `is_active` with `server_default=sa.true()`
- 4 indexes: `ix_recommendations_cbm_id`, `ix_recommendations_entity_id`, `ix_recommendations_recommendation_key`, `ix_recommendations_dimension`
- `downgrade()` drops all indexes before dropping table

**`services/models.py`** — `Recommendation` ORM model appended after `InterventionOutcome` (model #15):
- 18 columns mirroring migration schema
- `is_active = Column(Boolean, nullable=False, default=True)` — Python-side default
- `created_at` / `updated_at` with `default=datetime.utcnow` and `onupdate=datetime.utcnow`
- No FK constraints — consistent with existing pattern

**`services/recommendation_tracking_service.py`** (new):
- `_SafeEncoder` — `json.JSONEncoder` subclass; converts `datetime` → ISO-8601, `Decimal` → float, anything else → `str(obj)`. Never silently discards context; only catastrophic failures (circular reference) fall back to `'{}'`, always logged.
- `_serialize_context(context: dict) -> str` — wraps `json.dumps` with `_SafeEncoder`; logged fallback to `'{}'`
- `RecommendationTrackingService.record()` — idempotent: returns existing active row for same `(cbm_id, recommendation_key)` without inserting duplicate. Non-fatal: exception → rollback → return `None`.
- `RecommendationTrackingService.invalidate()` — sets `is_active=False`, `invalidated_at`, `invalidation_reason`. No-op when row not found. Non-fatal.

**`services/recommendation_learning_service.py`** (new):
- `RecommendationLearningService.get_success_rates(db, *, dimension, risk_level, min_sample=10) -> list[dict]`:
  - Joins `AI_ChatBot_Recommendations` to `AI_ChatBot_InterventionOutcomes` on `cbm_id`
  - Filters `eligible_for_learning=True` and `is_active=True`; optional `dimension` / `risk_level` filters
  - Groups by `recommendation_key`; computes `success_rate = total_improved / total_eligible` (None when 0)
  - `has_sufficient_sample = total_eligible >= min_sample`
  - Returns `[]` on any exception
- `RecommendationLearningService.get_ranked_keys(db, candidates, ...) -> list[str]`:
  - Sufficient-sample keys sorted by `success_rate` descending
  - Insufficient-sample and unknown candidates appended in original order
  - No candidates are ever removed
  - Returns original candidate list on any exception

**`services/mentor_message_service.py`** — Phase 4 integration:
- `from services.recommendation_tracking_service import RecommendationTrackingService` added
- 4 additional fields captured from session block: `trigger_type`, `trigger_level`, `trigger_kpi`, `trigger_severity`
- `RecommendationTrackingService().record()` called non-fatally after each `InterventionOutcomeService().enroll()` call — both on success path and on delivery-failed path
- `recommendation_key` derived as `f"{trigger_type}_{trigger_level}".lower().replace(" ", "_")` (falls back to `"unknown"`)
- `recommendation_context` is a frozen dict of `{trigger_type, trigger_level, kpi, severity}`
- No changes to return values or error propagation

### Validation

| File | Tests | Result |
|---|---|---|
| `tests/unit/test_recommendation_tracking_service.py` | 32 (3 classes) | **32 passed** (re-confirmed 2026-06-04 post-Sprint-4-commit) |
| `tests/unit/test_recommendation_learning_service.py` | 29 (2 classes) | **29 passed** (re-confirmed 2026-06-04 post-Sprint-4-commit) |
| `tests/unit/test_mentor_message_trigger.py` | 17 + 1 skipped | **17 passed, 1 skipped** (Sprint 5 + Sprint 6 classes; file is mixed — staged whole in combined commit) |
| **Sprint 6 unit gate total** | **61** | **61 passed, 0 failed** (0.87 s — 2026-06-04) |

`test_recommendation_tracking_service.py` classes: `TestSerializeContext` (8), `TestRecord` (17), `TestInvalidate` (7).
`test_recommendation_learning_service.py` classes: `TestGetSuccessRates` (18), `TestGetRankedKeys` (11 including edge cases: tied rates, None success_rate, DB error recovery, ranked-before-unranked ordering).
`test_mentor_message_trigger.py` additions (class `TestRecommendationTrackingTriggered`, 4 tests): tracking called after successful delivery, tracking called after failed delivery, tracking failure does not break `process_trigger`, tracking receives correct context dict.

### Self-Annealing Events

| Failure | Root Cause | Fix |
|---------|------------|-----|
| `test_is_active_defaults_true` returned `None` | ORM `default=True` fires during INSERT processing, not at object construction; mock `refresh()` is no-op | Explicitly pass `is_active=True` in `Recommendation(...)` constructor call inside `record()` |

### Risks / Limitations
- All Sprint 6 changes are UNCOMMITTED — will be committed as part of combined Sprint 5+6 commit
- **Combined Sprint 5+6 commit strategy**: `services/mentor_message_service.py` and `tests/unit/test_mentor_message_trigger.py` contain Sprint 5 and Sprint 6 changes interleaved — staging them separately is not viable; both files are staged whole in the combined commit
- **Sprint 7 exclusion required even in combined commit**: `alembic/versions/0014_add_recommendation_candidate_pools.py` is excluded entirely; `RecommendationCandidatePool` class (#16) in `services/models.py` must be excluded via `git add -p` — only the `InterventionOutcome` (#14) and `Recommendation` (#15) class hunks are staged
- ~~No directive for `RecommendationTrackingService` and `RecommendationLearningService`~~ — **RESOLVED 2026-06-04**: `directives/recommendation_learning_contract.md` created (479 lines); idempotency rule, `_SafeEncoder` priority, `success_rate` formula, `min_sample=10`, ranking algorithm, no-candidate-dropped guarantee, and LLM prohibition documented
- Migration 0013 not yet applied to SQL Server — `AI_ChatBot_Recommendations` table does not exist in any live DB
- ~~Phase 6 (E2E validation tests) not yet written~~ — `tests/e2e/test_recommendation_learning_flow.py` written (7 tests in `TestRecommendationLearningFlow`); skipping locally; DB validation pending once migration 0013 is applied
- `recommendation_key` derivation in `mentor_message_service.py` is mechanical (`type_level` pattern) — future improvement: lookup from a key registry

### Maturity
- `Recommendation` ORM model — **Tested**
- Migration 0013 — **Integrated** (file exists; not yet applied to any DB)
- `RecommendationTrackingService` — **Tested** (32 tests passing as of 2026-06-04)
- `RecommendationLearningService` — **Tested** (29 tests passing as of 2026-06-04)
- `mentor_message_service.py` integration — **Tested**
- E2E flow (`test_recommendation_learning_flow.py`) — **Integrated** (7 tests written; skipping locally; DB validation pending)
- `directives/recommendation_learning_contract.md` — **Integrated** (479 lines; 14 sections; idempotency rule, _SafeEncoder priority, success_rate formula, min_sample=10, ranking algorithm, no-candidate-dropped guarantee, LLM prohibition)

---

## Sprint 7 — Adaptive Recommendation Service (Full Implementation)
**Date: 2026-06-07 | Status: UNCOMMITTED — READY FOR COMMIT REVIEW**
**Status: Implemented + Tested (34 unit tests passing, 0 failed)**

### What Changed (uncommitted / untracked)

**`services/adaptive_recommendation_service.py`** (new, untracked — 152 lines):
- `AdaptiveRecommendationService.select_key(db, trigger_type, dimension, risk_level, fallback_key) → str`
- Pool lookup: queries `AI_ChatBot_RecommendationCandidatePools` by `(trigger_type, dimension, is_active=True)`
- Candidate parsing: `json.loads(pool.candidate_keys_json or "[]")` — returns `fallback_key` on empty or malformed JSON
- Parameter resolution: `epsilon_override` (NULL → `_DEFAULT_EPSILON = 0.05`), `min_sample_override` (NULL → `_DEFAULT_MIN_SAMPLE = 10`)
- Ranking: delegates to `RecommendationLearningService.get_ranked_keys()` — sufficient-sample keys ranked by success rate; unranked appended in original order; no candidate dropped
- Epsilon-greedy selection: `draw < epsilon` → `random.choice(candidates)` (exploration over full pool); else → `ranked[0]` (exploitation)
- Defensive contract: all exceptions caught at outer `try/except`; `fallback_key` always returned on any failure; never raises

**`alembic/versions/0014_add_recommendation_candidate_pools.py`** (new, untracked):
- revision="0014", down_revision="0013"
- Creates `AI_ChatBot_RecommendationCandidatePools` — governance-controlled pool definitions
- Maps one trigger context (`trigger_type + dimension` composite UNIQUE) to an ordered JSON array of candidate `recommendation_key` strings
- Columns: `id`, `created_at`, `updated_at`, `trigger_type` (String 50), `dimension` (String 50), `candidate_keys_json` (Text, NOT NULL — minimum valid value `'[]'`), `min_sample_override` (Integer, nullable — NULL → system default 10), `epsilon_override` (Float, nullable — NULL → system default 0.05), `is_active` (Boolean, `server_default=True`)
- 2 indexes: `uq_candidate_pools_trigger_dimension` (composite UNIQUE), `ix_candidate_pools_is_active`
- `downgrade()` drops both indexes before dropping table
- Soft-disable via `is_active=False`; rows are never deleted (pool definition history preserved for audit)
- No FK constraints — consistent with all other Sentinel tables

**`services/models.py`** — `RecommendationCandidatePool` ORM model appended (model #16, modified/uncommitted):
- `__tablename__ = "AI_ChatBot_RecommendationCandidatePools"`
- `UniqueConstraint("trigger_type", "dimension", name="uq_candidate_pools_trigger_dimension")`
- 9 columns mirroring migration schema
- `candidate_keys_json` — service layer is responsible for JSON serialize/deserialize; raw text must never be stored
- `min_sample_override` / `epsilon_override` — nullable; NULL delegates to `AdaptiveRecommendationService` system defaults
- No ORM relationships declared — service layer joins explicitly by `trigger_type + dimension`
- No FK constraints — consistent with existing pattern

**`services/mentor_message_service.py`** — `AdaptiveRecommendationService` wired (modified/uncommitted):
- `from services.adaptive_recommendation_service import AdaptiveRecommendationService` added to imports
- Wired at **both** recommendation tracking call sites (success path and delivery-failed/exception path)
- `_fallback_key` computed as `f"{trigger_type}_{trigger_level}".lower().replace(" ", "_")` — mechanical formula preserved as fallback when no pool row exists
- `recommendation_key = AdaptiveRecommendationService().select_key(db=rec_session, trigger_type=..., dimension=trigger_kpi or "general", risk_level=trigger_level, fallback_key=_fallback_key)` — replaces prior hardcoded derivation
- Both call sites pass `recommendation_key` (not `_fallback_key`) to `RecommendationTrackingService().record()`

**`directives/adaptive_recommendation_contract.md`** (new, untracked):
- Documents epsilon-greedy selection algorithm, pool lookup contract, `_DEFAULT_EPSILON=0.05`, `_DEFAULT_MIN_SAMPLE=10`
- Defines fallback degradation guarantee, LLM prohibition, and defensive contract
- Documents the wiring call site in `MentorMessageService.process_trigger()`

### Validation

| File | Tests | Result |
|---|---|---|
| `tests/unit/test_adaptive_recommendation_service.py` | 30 (7 classes) | **30 passed** (2026-06-07) |
| `tests/unit/test_mentor_message_trigger.py` → `TestAdaptiveRecommendationWiring` | 4 (1 class) | **4 passed** (2026-06-07) |
| **Sprint 7 unit gate total** | **34** | **34 passed, 0 failed** (2.86 s — 2026-06-07) |

`test_adaptive_recommendation_service.py` classes: `TestPoolLookup` (4), `TestCandidateParsing` (5), `TestEpsilonGreedyExploitation` (3), `TestEpsilonGreedyExploration` (2), `TestAdaptiveParameters` (6), `TestLearningServiceIntegration` (4), `TestDefensiveness` (6).

`TestAdaptiveRecommendationWiring` (4 tests): `select_key` called on successful delivery with correct kwargs; `select_key` called on delivery-failed path; `select_key` failure absorbed, `process_trigger` returns normally; `record()` receives key from `select_key()` not mechanical fallback formula.

### Risks / Limitations
- All Sprint 7 changes are UNCOMMITTED — 4 untracked files + 2 modified tracked files
- Migration 0014 not yet applied to any DB — `AI_ChatBot_RecommendationCandidatePools` table does not exist in any live environment; service degrades gracefully (returns `fallback_key`) when table is absent
- No E2E test for `AdaptiveRecommendationService` against live SQL Server — functional correctness validated by unit tests against mocked DB; E2E deferred until migration 0014 is applied

### Maturity
- `RecommendationCandidatePool` ORM model — **Tested** (via service tests; uncommitted)
- Migration 0014 — **Integrated** (file exists; not yet applied to any DB)
- `AdaptiveRecommendationService` — **Tested** (30 unit tests passing; uncommitted)
- `mentor_message_service.py` wiring — **Tested** (4 wiring tests passing; uncommitted)
- `directives/adaptive_recommendation_contract.md` — **Integrated** (exists; uncommitted)

---

## Sprint 8 — Governance Gate: Approval-Gated Delivery
**Date: 2026-06-12 (implementation) | 2026-06-17 (directive hardening + wiring test completion)**
**Status: Tested — 81 passed, 1 skipped (targeted Sprint 8 gate run 2026-06-17)**

### What Changed (uncommitted)

**`services/governance_gate_service.py`** (new, untracked — 68 lines):
- `GovernanceGateService.check_delivery_approved(db, entity_id, entity_type="student") → dict`
- Implements FR-EXEC-001: Approval-Gated Execution from `directives/governance_gate_contract.md`
- **Step 1** — queries `AIInterpretation` filtered by `entity_id`, `entity_type`, `is_active=True`, ordered by `created_at DESC`, limit 1
- **Step 2** — queries `GovernanceReview` filtered by `interpretation_id`, ordered by `created_at DESC`, limit 1; Step 2 is never issued when Step 1 returns no row
- Seven fixed outcomes with deterministic approved/reason/review_id values:
  - `approved_review` → `approved=True` — human reviewer confirmed the AI assessment; delivery proceeds
  - `pending` → `approved=False` — review queue not yet worked; delivery blocked
  - `rejected` → `approved=False` — reviewer disputed the AI interpretation; delivery blocked
  - `deferred` → `approved=False` — reviewer requested more information; delivery blocked
  - `no_governance_review` → `approved=False` — interpretation exists but no review row (pipeline fault); delivery blocked; logged at ERROR
  - `no_sentinel_data` → `approved=True` — no active interpretation; legacy fall-through; delivery proceeds unchanged
  - `gate_error` → `approved=True` — any unhandled DB exception; fail-open; logged at ERROR
- Read-only: no `db.commit()`, `db.add()`, `db.rollback()`, or write operations
- Never raises; always returns `{"approved": bool, "reason": str, "review_id": int | None}`
- No LLM calls; no heuristic auto-approval; no time-based logic — fully deterministic

**`services/mentor_message_service.py`** — governance gate wired (modified/uncommitted):
- `from services.governance_gate_service import GovernanceGateService` added to imports
- Gate check inserted after the atomic `UPDATE Completed=1 RETURNING` claim commits and the main session closes, before `OutboundDeliveryService.send_text()`
- Gate runs in a dedicated read-only `SessionLocal()` (`gate_session`) — not shared with claim session or write paths
- `entity_id=str(user_id) if user_id is not None else ""` — caller-side integer-to-string cast as specified by directive Section 4.3
- If `gate_result["approved"]` is `False`: returns `{"sent": False, "reason": "governance_review_required", "review_id": gate_result.get("review_id"), "cbm_id": cbm_id}` without calling `send_text()`
- If `gate_result["approved"]` is `True`: existing delivery flow continues unchanged
- Gate call wrapped in `try/except Exception` — any exception (including mock side_effect) is fail-open; `print([WARNING] ...)` emitted; delivery proceeds
- Gate is **not** called on: `no_db` early return, `not_found` early return, `already_claimed` early return

**`directives/governance_gate_contract.md`** — directive hardened (2026-06-17):
- Gap analysis completed — 4 items resolved:
  1. Section 9 wiring table was missing required tests for `no_db` and `not_found` early-exit gate skips (only `already_claimed` was covered); both added
  2. Section 9 and Section 10 DoD were misaligned on `gate_error` coverage — DoD required testing the internal `gate_error` return value; Section 9 table only listed an outer-exception test; now distinct required entries; outer-exception test labelled supplementary/optional
  3. Section 7 blocked return shape (`"governance_review_required"`) lacked rationale for normalization; paragraph added explaining why granular gate reason is not passed through to the caller
  4. Section 9 / Section 10 naming confusion — DoD referenced phantom class `TestGovernanceGateService` instead of the file `tests/unit/test_governance_gate_service.py`; Section 9 coverage group column renamed; both corrected

### Validation

| File | Tests | Result |
|---|---|---|
| `tests/unit/test_governance_gate_service.py` | 50 (7 classes) | **50 passed** (2026-06-12) |
| `tests/unit/test_mentor_message_trigger.py` → `TestGovernanceGateWiring` | 10 (1 class) | **10 passed** (2026-06-17; 3 tests added: `gate_error` return path, `not_found` skip, `entity_id` str cast) |
| **Sprint 8 governance gate total** | **60** | **60 passed, 0 failed** |
| **Targeted Sprint 8 run** (both files combined) | **81 + 1 skip** | **81 passed, 1 skipped** (3.08 s — 2026-06-17; skip = MSSQL integration test, expected in local env) |

`test_governance_gate_service.py` classes:
- `TestApprovedPath` (4) — active interpretation + approved review → `approved_review`; `review_id` is integer matching review row
- `TestBlockedPaths` (9) — pending / rejected / deferred: all `approved=False`; all have integer `review_id`
- `TestNoGovernanceReview` (3) — active interpretation, no review row → `no_governance_review`; `approved=False`; `review_id=None`
- `TestNoSentinelData` (4) — no active interpretation → `no_sentinel_data`; `approved=True`; `review_id=None`; Step 2 query never issued
- `TestNoSentinelDataEdgeCases` (3) — empty string entity_id → `no_sentinel_data`; invalidated-only (mock returns None) → `no_sentinel_data`
- `TestFailOpen` (6) — DB exception → `gate_error`; `approved=True`; never raises; `logger.error` called with `entity_id`; fail-open semantics
- `TestReturnContract` (21) — all 7 outcomes return dict; `approved` key always present; `reason` always `str`; `review_id` always `int` or `None`; `approved` is real `bool`

`TestGovernanceGateWiring` (7 tests):
- `test_approved_gate_calls_send_text` — gate `approved=True` → `send_text()` called once
- `test_pending_gate_does_not_call_send_text` — gate `approved=False` → `send_text()` call_count == 0
- `test_pending_gate_returns_governance_review_required_shape` — `sent=False`, `reason="governance_review_required"`, `review_id`, `cbm_id` all present and correct
- `test_no_sentinel_data_gate_calls_send_text` — `no_sentinel_data` (approved=True) → `send_text()` called (legacy fall-through preserved)
- `test_gate_exception_is_fail_open_send_text_called` — gate raises → fail-open → `send_text()` called
- `test_gate_not_called_on_already_claimed_path` — gate called exactly once; `already_claimed` second call skips gate
- `test_gate_not_called_on_no_db_path` — `MSSQL_CONFIGURED=False` early return; gate never called
- `test_gate_error_outcome_calls_send_text` — gate service returns `{"approved": True, "reason": "gate_error", "review_id": None}`; `send_text()` called once; internal fail-open return path distinct from outer exception guard
- `test_gate_not_called_on_not_found_path` — `MSSQL_CONFIGURED=True`, `cbm_id=999999` absent from DB; returns `not_found`; gate never called
- `test_gate_called_with_string_entity_id_when_user_id_is_integer` — `UserID=101` integer; gate receives `entity_id="101"` as `str`; verifies `str(user_id)` cast in `process_trigger()`

### Risks / Limitations
- All Sprint 8 changes are UNCOMMITTED — 1 untracked file (`governance_gate_service.py`, `test_governance_gate_service.py` already tracked) + 1 modified tracked file (`mentor_message_service.py`, `test_mentor_message_trigger.py` already modified)
- `governance_gate_contract.md` was pre-existing as an untracked file; it must be staged in the Sprint 8 commit
- FR-EXEC-001 is **partially** satisfied: gate logic is implemented and wired; governance review workflow (approve/reject/defer via API) existed since Sprint 3 (`GovernanceReviewService`); full end-to-end (reviewer calls API → delivery unblocked) not yet E2E tested
- Gate uses a new `SessionLocal()` for each trigger — adds one additional DB connection per process_trigger call; no connection pooling concern at current scale
- `gate_error` fail-open is intentional per directive Section 5: monitoring layer must not become a single point of failure for the production engagement pipeline; this policy requires explicit architectural approval to change

### Maturity
- `GovernanceGateService` — **Tested** (50 unit tests passing; uncommitted)
- Governance gate wiring (`mentor_message_service.py`) — **Tested** (10 wiring tests passing; uncommitted)
- `directives/governance_gate_contract.md` — **Verified** (4 directive gaps resolved 2026-06-17: missing test requirements for no_db/not_found skip paths, gate_error/exception alignment, normalization rationale added, naming clarity fixed)

---

## Pending Work

### Immediate (Sprint 8 commit gate — READY)
- [x] ~~Implement `GovernanceGateService`~~ — **Resolved 2026-06-12**: 68-line service; 7-outcome deterministic contract; read-only; never raises; 50 unit tests passing
- [x] ~~Write unit tests for `GovernanceGateService`~~ — **Resolved 2026-06-12**: 50 tests in 7 classes covering all 7 outcomes, fail-open, and return contract
- [x] ~~Wire `GovernanceGateService` into `MentorMessageService`~~ — **Resolved 2026-06-12**: gate inserted after claim commit, before `send_text()`; fail-open; 7 wiring tests in `TestGovernanceGateWiring` passing
- [ ] Commit Sprint 8 as a single logical changeset — 81 passed, 1 skipped; files to stage: `services/governance_gate_service.py` (new), `tests/unit/test_governance_gate_service.py` (new), `directives/governance_gate_contract.md` (modified), `services/mentor_message_service.py` (modified), `tests/unit/test_mentor_message_trigger.py` (modified)

### Immediate (Sprint 7 commit gate — READY)
- [x] ~~Implement `AdaptiveRecommendationService`~~ — **Resolved 2026-06-07**: 152-line service implemented; epsilon-greedy selection; defensive fallback contract; 30 unit tests passing
- [x] ~~Write unit tests for `AdaptiveRecommendationService`~~ — **Resolved 2026-06-07**: 30 tests in 7 classes; all passing
- [x] ~~Wire `AdaptiveRecommendationService` into pipeline~~ — **Resolved 2026-06-07**: wired at both call sites in `mentor_message_service.py`; 4 wiring tests in `TestAdaptiveRecommendationWiring` passing
- [x] ~~Write directive for `AdaptiveRecommendationService`~~ — **Resolved 2026-06-07**: `directives/adaptive_recommendation_contract.md` created
- [ ] Commit Sprint 7 as a single logical changeset (4 untracked files: `adaptive_recommendation_service.py`, `test_adaptive_recommendation_service.py`, `0014_add_recommendation_candidate_pools.py`, `adaptive_recommendation_contract.md`; 2 modified files: `services/models.py`, `services/mentor_message_service.py`)
- [ ] Apply migration 0014 to SQL Server only after commit lands

### Immediate (Sprint 5+6 DB validation gate)
- [x] ~~Commits for Sprints 5 and 6~~ — **Resolved 2026-06-04**: committed as `fd983e6 feat: Sprint 5+6 — outcome learning and recommendation tracking pipeline`
- [ ] Run `alembic upgrade head` against SQL Server to create `AI_ChatBot_InterventionOutcomes` (migration 0012) and `AI_ChatBot_Recommendations` (migration 0013)
- [ ] Set `MSSQL_DATABASE_URL` and run `pytest tests/e2e/test_outcome_learning_flow.py tests/e2e/test_recommendation_learning_flow.py -v` — expect 11 + 7 = 18 passed; E2E fixture fixes applied (raw SQL INSERT, 10ms tolerance, GroupStatus/ChatGPT_prompt/DataDictionary columns)
- [ ] Confirm rows created and cleaned up correctly after E2E runs

### High Priority (carry-forward)
- [ ] Add trigger deduplication guard in `DbTriggerProcessingService.process()` — prevent double-queuing
- [ ] Apply Alembic migrations 0008–0011 against dev/staging DB and verify schema integrity
- [ ] Browser-test SentinelDashboard — confirm components render correctly with mock data
- [ ] Remove `tmp/staging_claim_test.py` from tracked files (tmp/ should not be committed)

### Medium Priority
- [ ] Replace bare `except Exception: pass` at audit log call sites with `logger.error(...)` for visibility
- [ ] Add `entity_id` `min_length=1` validation on `InsightGenerateRequest`
- [ ] Disable FastAPI docs in production (`docs_url=None` when `DISABLE_DOCS=1`)
- [ ] E2E test `POST /sentinel/evaluate` end-to-end with mock mode

### Provider Integrations (Scaffolded, Not Wired)
- [ ] Twilio SMS — stub in place, integration point commented
- [ ] Twilio WhatsApp — stub in place, integration point commented
- [ ] Twilio Voice — stub in place, integration point commented
- [ ] Mandrill Email — stub in place, integration point commented; real integration deferred

---

## Self-Annealing Loop Record

| Date | Failure | Root Cause | Fix | Directive Updated |
|------|---------|------------|-----|-------------------|
| 2026-04-21 | Worker silently skipped all triggers locally | `SessionLocal is None` always false (SQLite fallback) | Replace with `MSSQL_CONFIGURED` | — |
| 2026-04-21 | Double-send risk on retry | `send_text()` called before commit | Commit `Completed=1` before send | — |
| 2026-04-21 | `send_text()` always returned `True` | Unconditional `return True` regardless of delivery outcome | Propagate `delivery_results`, compute truth via `any()` | `outbound_delivery_contract.md` |
| 2026-04-21 | `init_local_db.py` could run against production | No environment gate | Add `MSSQL_CONFIGURED` guard + `sys.exit(1)` | `database_safety.md` |
| 2026-04-21 | 2 insight tests failing | `explanation`/`recommended_action` in schema but not in directive | Remove fields from `InsightResponse` | — |
| 2026-04-21 | 7 delivery tests failing | `send_text()` return type changed, tests not updated | Update all assertions to `isinstance(result, list)` | — |
| 2026-04-21 | `DeliverySucceeded` NULL on exception path | `process_trigger` except block returned before write-back | Write `False` in except block before return | — |
| 2026-04-21 | Retry wrote hardcoded `False` instead of intended value | Retry used literal `False`, breaking NULL semantics for no-attempt case | Retry uses `delivery_succeeded` variable (None/True/False) | — |
| 2026-04-21 | Tests for Cases C and E passed trivially | `MSSQL_CONFIGURED=False` caused early `no_db` return; function never reached write-back | Patch `MSSQL_CONFIGURED=True` in all 5 `TestDeliverySucceededWriteback` tests | — |
| 2026-05-20 | AI prompt produced jargon-heavy output not usable by advisors | Prompt used internal terms: "entity", "KPI", "behavioral fingerprint", "sentinel" | Rewrote system prompt + added `_KPI_LABEL_MAP` to translate signal names before sending to Claude | — |
| 2026-05-20 | Fingerprints not available to AI insight call | `FingerprintGeneratorService` existed but was never wired into orchestration | Added Step 1b in `SentinelOrchestrationService._run_pipeline()` — generate+persist before AI call; append to `current_fingerprints` | — |
| 2026-05-28 | `InsightGenerator` generated insight for every KPI regardless of health | No severity or suppress logic existed; all KPIs produced insights | Added `interpret_kpi()` with per-KPI thresholds; `suppress=True` for healthy signals; `InsightGenerator` skips suppressed KPIs | — |
| 2026-05-28 | `AIInterpretation` join to `TriggeredUsers` by user ID would silently fail | `entity_id` is `String(100)` but `UserID` is `Integer` — type mismatch at join | Application-layer coercion `entity_id = str(user_id)` documented in model, service, and comments throughout | — |
| 2026-05-30 | E2E `_insert_trigger_data()` raised `IDENTITY INSERT` error against real SQL Server | `mapped_column(Integer, primary_key=True)` triggers MSSQL dialect `SET IDENTITY_INSERT ON` when explicit PK is supplied; real column has no IDENTITY property | Replaced ORM insert with `session.execute(text("INSERT INTO ..."), {...})` raw SQL | — |
| 2026-05-30 | E2E `evaluated_at` assertion failed by ~2 ms against real SQL Server | SQL Server `DATETIME` rounds to ~3.33 ms; Python `datetime.utcnow()` captures microseconds; stored value can round below capture point | Changed assertion to `>= before_eval - timedelta(milliseconds=10)` | — |
| 2026-05-30 | E2E insert failed with `Cannot insert NULL into column 'GroupStatus'` | Real SQL Server `AI_ChatBot_TriggerData` has additional NOT NULL columns (`GroupStatus`, `ChatGPT_prompt`, `DataDictionary`) not in original fixture | Added all three columns to the raw SQL INSERT in `_insert_trigger_data()` | — |
| 2026-05-30 | `test_is_active_defaults_true` returned `None` instead of `True` | ORM `Column(Boolean, default=True)` fires during INSERT processing, not at object construction; mock `refresh()` is no-op so attribute stayed `None` | Explicitly pass `is_active=True` in `Recommendation(...)` constructor call inside `record()` | — |
| 2026-06-03 | `SENTINEL_DEBUG_PAYLOAD` logs firing at INFO level in production — full KPI + fingerprint JSON emitted on every evaluation | All 9 `SENTINEL_DEBUG_PAYLOAD` format-string calls used `logger.info()` instead of `logger.debug()` | Changed all 9 occurrences to `logger.debug()` in `sentinel_orchestration_service.py`; silent at INFO in production, accessible with DEBUG log level | — |
