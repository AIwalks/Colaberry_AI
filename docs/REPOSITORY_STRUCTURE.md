# Repository Structure
**Colaberry Sentinel OS | Last updated: 2026-05-07 | Sprint 0**

This document is the canonical onboarding index for the repository.
Start here, then follow links to the appropriate layer.

---

## Quick Start for New Engineers

1. Read [CLAUDE.md](../CLAUDE.md) — the operating contract (10 min)
2. Read [docs/architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md) — what the system does (10 min)
3. Read [docs/mvp/MVP_SCOPE.md](mvp/MVP_SCOPE.md) — what to build next (5 min)
4. Read [audit/IMPLEMENTATION_SEQUENCE.md](../audit/IMPLEMENTATION_SEQUENCE.md) — sprint-by-sprint plan (15 min)

Do not read anything in `archive/` — it is historical only.

---

## Directory Map

### Active Code

| Directory | Layer | Purpose |
|---|---|---|
| `app/` | API boundary | FastAPI entry point, lifespan, CORS, route registration |
| `api/routes/` | API boundary | Sub-routers: directives, fingerprint, kpi, insight |
| `api/schemas/` | API boundary | Pydantic request/response schemas |
| `services/` | Business logic | Trigger processing, mentor messages, delivery, audit, models |
| `services/worker/` | Runtime | Polling worker — the actual execution loop |
| `core/fingerprint/` | Intelligence | Behavioral fingerprint evaluation (threshold math) |
| `core/insight/` | Intelligence | Insight generation (template-based; Claude API in Sprint 2) |
| `core/kpi_discovery/` | Intelligence | KPI discovery (hardcoded stub; replace Sprint 2) |
| `skills/insight_explainer/` | Intelligence | Insight explanation (keyword matching; replace Sprint 2) |
| `config/` | Configuration | Database, auth, logging, request context |
| `execution/` | Scripts | db_reflect.py, directive_registry.py, init scripts |
| `alembic/` | Migrations | Additive-only DB migrations (never modifies production tables) |
| `frontend/` | UI shell | React app (blank page; build in Sprint 4) |

### Tests

| Directory | Purpose |
|---|---|
| `tests/unit/` | Fast, mocked unit tests — 25+ passing |
| `tests/integration/` | Tests that may touch dev sandbox or DB |
| `tests/e2e/` | Browser/API end-to-end tests |

### Governance & Documentation

| Directory | Status | Purpose |
|---|---|---|
| `audit/` | **Canonical** | System audit — authoritative engineering governance (13 files) |
| `docs/` | **Canonical** | Onboarding documents (this file + 3 others) |
| `spec/` | **Canonical** | Requirements: FR-GOV-001, FR-EXEC-001 (1 file) |
| `directives/` | **Canonical** | Operational SOPs and behavioral contracts (10 files) |
| `CLAUDE.md` | **Canonical** | AI operating contract — must be read first |
| `integration/` | Minimal | 1 file: `platform_operational_maturity_model.md` (strategic roadmap) |
| `implementation/` | Minimal | 1 file: `implementation_roadmap.md` (strategic direction only) |

### Design Documentation (not yet audited — may contain aspirational content)

| Directory | Files | Purpose |
|---|---|---|
| `architecture/` | 6 | Component architecture designs |
| `data/` | 9 | Data governance and schema policies |
| `operations/` | 7 | Runbooks, incident response, capacity planning |
| `security/` | 1 | Security architecture model |
| `state/` | 1 | System state model |
| `runtime/` | 1 | Runtime orchestration model |
| `environment/` | 1 | Environment configuration model |
| `evolution/` | 1 | Change/evolution strategy |
| `failure/` | 1 | Failure playbook |
| `meta/` | 1 | System meta operating contract |
| `ux/` | 1 | User experience interaction model |

> **Note:** These directories were not part of the Sprint 0 audit scope. They contain no doctrine-clone language. Review and validate against actual implementation before treating as authoritative.

### Archive

| Directory | Purpose |
|---|---|
| `archive/constitutional_doctrine/` | 29 archived template-based governance docs (historical only) |

See [archive/constitutional_doctrine/README.md](../archive/constitutional_doctrine/README.md) for context.

### Scratch

| Directory | Purpose |
|---|---|
| `tmp/` | Scratch space — always safe to delete, never committed |
| `agents/` | Agent persona definitions — no executable logic |
| `workers/` | Worker module stub |

---

## Root Files

| File | Purpose |
|---|---|
| `CLAUDE.md` | **Read first.** AI operating contract and coding rules |
| `README.md` | Project introduction and folder table |
| `PROGRESS.md` | Session log and work tracker |
| `alembic.ini` | Alembic migration configuration |
| `conftest.py` | Pytest fixtures (shared test configuration) |
| `requirements.txt` | Python dependencies |
| `.pre-commit-config.yaml` | Pre-commit hooks (linting) |
| `.gitignore` | Git ignore rules (local.db, secrets, __pycache__) |
| `local.db` | SQLite dev database — NOT committed (in .gitignore) |

---

## The `audit/` Directory — Read This First

The `/audit/` directory is the authoritative engineering governance layer.
It was written with maximum rigor against the actual codebase (not aspirational descriptions).

| File | What It Contains |
|---|---|
| [README.md](../audit/README.md) | Index of audit deliverables |
| [CONFLICT_ANALYSIS.md](../audit/CONFLICT_ANALYSIS.md) | 9 conflicts between doctrine claims and code reality |
| [CANONICAL_ARCHITECTURE.md](../audit/CANONICAL_ARCHITECTURE.md) | What the system actually is (runtime topology, service map) |
| [DOMAIN_MODEL.md](../audit/DOMAIN_MODEL.md) | All 12 entities with field-level truth from actual ORM |
| [EVENT_MODEL.md](../audit/EVENT_MODEL.md) | Audit trail vs. replay — what exists, what doesn't |
| [GOVERNANCE_MODEL.md](../audit/GOVERNANCE_MODEL.md) | Complete GovernanceApprovalService specification |
| [IMPLEMENTATION_SEQUENCE.md](../audit/IMPLEMENTATION_SEQUENCE.md) | Sprint 0–5 tactical plan with exact tasks |
| [TECHNICAL_DEBT_RISKS.md](../audit/TECHNICAL_DEBT_RISKS.md) | Risk register with severity, effort, sprint assignment |
| [MVP_RECOMMENDATION.md](../audit/MVP_RECOMMENDATION.md) | Concept classification: Required/Future/Ceremonial/Delete |
| [FINAL_RECOMMENDATION.md](../audit/FINAL_RECOMMENDATION.md) | Final MVP stack, architecture, removal list |
| [REMOVE_OR_DEFER_LIST.md](../audit/REMOVE_OR_DEFER_LIST.md) | What was deleted, archived, kept, and why |

---

## Invariants That Must Hold (from CLAUDE.md)

```
1. No sprint deploys without all tests passing
2. Every new service has a unit test for happy path AND at least one failure path
3. Every new DB table goes through Alembic (never manual schema changes)
4. MSSQL_DATABASE_URL must never appear in source code (env var only)
5. Production SQL Server tables (TriggerData, TriggerRules) must never be modified
6. Every sprint ends with an updated PROGRESS.md entry
7. The approval gate must never be disableable via a flag or env var
```
