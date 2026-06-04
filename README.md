# Colaberry AI — Sentinel OS

> **Agent-First, Deterministic-Execution** operational intelligence platform. AI reasons. Humans decide. Deterministic Python executes.

---

## What Is This

**Colaberry AI** is an AI-driven student support ecosystem that monitors students throughout their learning journey and communicates with them automatically through WhatsApp, email, SMS, and voice — reminders, follow-ups, motivational messages, learning support, all personalized.

**Sentinel OS** is the operational intelligence layer built on top of that. While Colaberry AI handles engagement and communication, Sentinel OS handles monitoring, intelligence, and visibility. Think of it as a real-time command center — continuously watching student KPIs, running them through an AI interpretation pipeline, and routing every recommendation through a human governance review queue before any automation fires.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Sentinel OS                             │
│                                                             │
│  Layer 1 — Directives                                       │
│  Human-readable SOPs, contracts, runbooks (no code)        │
│                    ↓                                        │
│  Layer 2 — Orchestration (Claude Code)                      │
│  Reads directives → plans → designs tests                   │
│                    ↓                                        │
│  Layer 3 — Execution (Deterministic)                        │
│  FastAPI + services + workers                               │
│                    ↓                                        │
│  Layer 4 — Verification                                     │
│  Unit, integration, and e2e tests                           │
└─────────────────────────────────────────────────────────────┘
```

### Sentinel Intelligence Pipeline

```
[Student KPI Data]
       ↓
[Extraction]        Read-only DB pull — normalizes student fingerprint
       ↓
[AI Interpretation] Claude API → risk_level, confidence, recommended_action, reasons
       ↓
[Material Change Gate] Has student state changed? Reuse cache or regenerate.
       ↓
[Governance Review] Every AI output queued as pending — nothing fires until approved
```

---

## Core Services

| Service | Purpose |
|---|---|
| `sentinel_orchestration_service.py` | Top-level pipeline coordinator |
| `ai_insight_service.py` | Claude API integration — risk assessment generation |
| `sentinel_extraction_service.py` | Read-only student KPI data pull |
| `material_change_evaluation_service.py` | Deterministic gate — reuse cache or regenerate |
| `governance_review_service.py` | Human review queue management |
| `trigger_processing_service.py` | KPI threshold evaluation and trigger firing |
| `mentor_message_service.py` | Outbound communication routing |
| `outbound_delivery_service.py` | WhatsApp / SMS / email / voice delivery |

---

## Repo Structure

```
├── app/                    FastAPI HTTP interface + API key auth
├── api/                    Routes and schemas
├── services/               Core intelligence pipeline services
├── agents/                 Agent personas and role definitions
├── workers/                Background and scheduled jobs
├── config/                 Environment wiring (no secrets)
├── alembic/                Schema versioning and migrations
├── tests/                  Unit, integration, and e2e tests
├── docs/
│   ├── architecture/       System architecture documents
│   ├── directives/         SOPs, contracts, and runbooks
│   ├── audit/              Gap analysis, risk reports, consistency checks
│   ├── data/               Data models, lineage, governance policies
│   └── operations/         Runbooks, incident response, SLOs
├── archive/                Deferred and reference documents
├── Claude.md               Operating contract for Claude Code
└── PROGRESS.md             Session log and sprint tracker
```

---

## Design Principles

**AI should reason. Deterministic systems should execute.**
Every Claude API response is treated as probabilistic output. It lands in a governance review queue as `pending`. No mentor message, alert, or automated action fires until a human approves it.

**One contract per behavior.**
Every service has a corresponding directive in `/docs/directives` — a human-readable SOP that defines exactly what that service is allowed to do.

**Test first, always.**
No logic ships without a corresponding test. The `/tests` folder covers unit, integration, and end-to-end scenarios.

---

## Stack

- **Python** — FastAPI, SQLAlchemy 2.0, Alembic
- **Database** — SQL Server (production), SQLite (local dev)
- **AI** — Anthropic Claude API
- **Auth** — API key authentication on all routes
- **Delivery** — Twilio (SMS/WhatsApp/Voice), Mandrill (email)
- **Testing** — pytest

---

## Related

- [Student_Intelligence_Platform](https://github.com/AIwalks/Student_Intelligence_Platform) — Microsoft Fabric implementation of the same architecture: Bronze/Silver/Gold lakehouse, PySpark pipelines, Fabric Data Agent
