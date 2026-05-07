# Colaberry Sentinel OS — System Overview
**Last updated: 2026-05-07 | Sprint 0**

---

## What This System Does

Sentinel OS monitors student KPI data in a Microsoft SQL Server database and sends personalized outreach messages (SMS, WhatsApp, or email) when a student's metrics cross configured thresholds. A polling worker evaluates pending triggers, generates messages, and delivers them via Twilio. All actions are logged to append-only audit tables.

**This is a student engagement chatbot.** It is not a distributed system, not an event-sourced platform, and not a civilization-preserving framework. The implementation is clean and correct for what it does.

---

## Runtime Topology

```
SQL Server (production — READ ONLY)
    AI_ChatBot_TriggerData   ← student KPI data
    AI_ChatBot_TriggerRules  ← threshold rules + message templates

        ↓  evaluated by

FastAPI (app/main.py)
    POST /ai/trigger/process     ← evaluates rule against student KPI
    POST /ai/mentor/message      ← handles inbound student replies
    + 4 sub-routers (directives, fingerprint, kpi, insight)

        ↓  writes pending work to

SQL Server (overlay — READ + WRITE)
    AI_ChatBot_TriggeredUsers    ← pending triggers (CBM_ID = spine)
    AI_ChatBot_ConversationState ← active conversation per phone/email

        ↓  consumed by

TriggerWorker (services/worker/trigger_worker.py)
    SELECT WHERE Completed=0     ← polling, not event-driven
    UPDATE SET Completed=1       ← atomic claim (prevents duplicate sends)
    → MentorMessageService       ← message generation (templates today; Claude API Sprint 2)
    → OutboundDeliveryService    ← Twilio SMS/WhatsApp or SMTP email

        ↓  writes outcomes to

Audit Tables (append-only)
    AI_ChatBot_AuditLog          ← message content
    AI_ChatBot_EngagementEvents  ← every action with CBM_ID
    AI_ChatBot_DeliveryLog       ← delivery success/failure
    AI_ChatBot_StudentResponses  ← inbound reply → trigger linkage
```

---

## Single Trigger Lifecycle (the core loop)

1. External caller → `POST /ai/trigger/process {trigger_type, student_id, event_id}`
2. `TriggerEvaluator` reads `TriggerRules` — finds matching rule for this student's KPI
3. **(Sprint 1 — NOT YET BUILT)** Severity gate: severity ≥ 3 creates `ApprovalRequest`, returns pending
4. `TriggeredUser` row inserted (`CBM_ID` assigned, `Completed=0`)
5. `TriggerWorker` picks it up in next poll cycle
6. Atomic claim: `UPDATE SET Completed=1 WHERE CBM_ID=?`
7. Message generated (today: template string from `ChatGPTPromptLowTrigger` column; Sprint 2: Claude API)
8. `OutboundDeliveryService` → Twilio sends SMS/WhatsApp
9. `DeliverySucceeded=True` written back to `TriggeredUser`
10. `DeliveryLog`, `EngagementEvent`, `ChatBotAuditLog` rows written
11. Student replies → `POST /ai/mentor/message` → `StudentResponse` linked to `CBM_ID`

**`CBM_ID` is the system-wide join key.** Every audit table links to it.

---

## What Is and Is Not Implemented

| Feature | Status | Sprint to Build |
|---|---|---|
| Trigger evaluation (threshold math) | ✓ Working | — |
| Atomic claim (no duplicate sends) | ✓ Working | — |
| Twilio SMS/WhatsApp delivery | ✓ Working (if env vars set) | — |
| Email delivery via SMTP | ✓ Working (if env vars set) | — |
| Append-only audit tables | ✓ Working | — |
| DeliverySucceeded writeback | ✓ Working | — |
| 25+ unit tests passing | ✓ Working | — |
| Governance approval gate | ✗ Missing | Sprint 1 |
| Real Claude API inference | ✗ Missing (templates only) | Sprint 2 |
| Inbound response handler | ✗ Missing (schema exists) | Sprint 2 |
| SQL Server observation layer | ✗ Missing (db_reflect.py unconnected) | Sprint 3 |
| Admin dashboard | ✗ Shell only | Sprint 4 |
| Production deployment | ✗ Not deployed | Sprint 5 |

---

## Key Directories

| Directory | Purpose |
|---|---|
| `app/` | FastAPI application entry point and routing |
| `services/` | Core business logic (trigger, message, delivery, models) |
| `services/worker/` | Polling worker — the actual runtime |
| `core/` | Intelligence layer (fingerprint, insight, KPI — all template-based) |
| `api/routes/` | Sub-routers for directives, fingerprint, KPI, insight endpoints |
| `config/` | Database connection, auth, logging, request context |
| `execution/` | Deterministic utility scripts (DB init, seed data, directive registry) |
| `alembic/` | Database migrations (additive-only overlay; never modifies production tables) |
| `tests/` | Unit, integration, and e2e test suites |
| `directives/` | Human-readable SOPs describing system behavior contracts |
| `spec/` | Canonical requirements (FR-GOV-001, FR-EXEC-001) |
| `audit/` | System audit — the authoritative engineering governance layer |
| `architecture/` | Architecture design documents (component designs) |
| `data/` | Data governance and schema documentation |
| `operations/` | Operational runbooks and procedures |

---

## Environment Variables Required

| Variable | Purpose | Required |
|---|---|---|
| `API_KEY` | API authentication header | ✓ Required |
| `MSSQL_DATABASE_URL` | SQL Server connection string | Production only (SQLite fallback in dev) |
| `TWILIO_ACCOUNT_SID` | Twilio SMS/WhatsApp | Optional (prints to stdout if absent) |
| `TWILIO_AUTH_TOKEN` | Twilio auth | Optional |
| `TWILIO_FROM_NUMBER` | Sender number | Optional |
| `EMAIL_HOST` | SMTP server | Optional |
| `EMAIL_FROM` | Sender email | Optional |
| `ANTHROPIC_API_KEY` | Claude API (Sprint 2) | Not yet required |

---

## Deeper Reading

- **Active sprint plan**: [audit/IMPLEMENTATION_SEQUENCE.md](../../audit/IMPLEMENTATION_SEQUENCE.md)
- **Governance model**: [audit/GOVERNANCE_MODEL.md](../../audit/GOVERNANCE_MODEL.md)
- **Domain model**: [audit/DOMAIN_MODEL.md](../../audit/DOMAIN_MODEL.md)
- **Technical debt register**: [audit/TECHNICAL_DEBT_RISKS.md](../../audit/TECHNICAL_DEBT_RISKS.md)
- **Requirements**: [spec/01_requirements.md](../../spec/01_requirements.md)
- **Operating contract**: [CLAUDE.md](../../CLAUDE.md)
