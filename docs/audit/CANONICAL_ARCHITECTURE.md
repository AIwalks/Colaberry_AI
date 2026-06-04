# CANONICAL ARCHITECTURE — MAXIMUM RIGOR EDITION
**Colaberry Sentinel OS | Date: 2026-05-07**

---

## PART A — WHAT THE SYSTEM ACTUALLY IS TODAY

### Definitive Description
Colaberry Sentinel OS is a **rule-based student outreach automation system** overlaid on an existing SQL Server CRM/LMS. It polls for student trigger events, selects a pre-written message template from the database, delivers that message via Twilio (SMS or WhatsApp) or SMTP email, and logs all activity in append-only audit tables.

There is no real-time AI inference in any production execution path. There is no event-driven architecture. There is no governance approval gate. There is no human-in-the-loop step before messages are sent.

This is a **well-built, useful, honest system** — the problem is not the system; it is the documentation claiming the system is something it is not.

---

## PART B — ACTUAL RUNTIME TOPOLOGY

```
┌─────────────────────────────────────────────────────────┐
│  SQL Server (Production — READ ONLY for most tables)     │
│                                                           │
│  AI_ChatBot_TriggerData     ← read (student KPI data)    │
│  AI_ChatBot_TriggerRules    ← read (evaluation rules)    │
│  AI_ChatBot_TriggeredUsers  ← read + write (trigger log) │
│  AI_ChatBot_ConversationState ← read + write             │
│  AI_ChatBot_AuditLog        ← write only                 │
└──────────────────────────────────┬──────────────────────┘
                                   │ pyodbc / SQLAlchemy 2.0
┌──────────────────────────────────▼──────────────────────┐
│  FastAPI App  (app/main.py)                              │
│                                                           │
│  POST /ai/trigger/process                                 │
│    → DbTriggerProcessingService                          │
│        → TriggerEvaluator (pure threshold logic)         │
│        → writes TriggeredUser row                        │
│        → logs EngagementEvent                            │
│                                                           │
│  POST /ai/mentor/message                                  │
│    → MentorMessageService.handle()                       │
│        → returns hardcoded string (no AI inference)      │
│        → logs ChatBotAuditLog + EngagementEvent          │
│                                                           │
│  GET/POST /api/directives/*                              │
│  GET/POST /api/fingerprint/*                             │
│  GET/POST /api/kpi/*                                     │
│  GET/POST /api/insight/*                                 │
└──────────────────────────────────┬──────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────┐
│  Trigger Worker  (services/worker/trigger_worker.py)     │
│  Runs on schedule (how? manual invocation or cron)       │
│                                                           │
│  SELECT * FROM TriggeredUsers WHERE Completed = 0        │
│    → For each CBM_ID:                                    │
│        MentorMessageService.process_trigger(cbm_id)      │
│            → reads message_text from TriggerRule.ChatGPT │
│              PromptLowTrigger (a stored VARCHAR string)  │
│            → UPDATE TriggeredUsers SET Completed=1       │
│              WHERE CBM_ID=? AND Completed=0              │
│              RETURNING CBM_ID  (atomic claim)            │
│            → OutboundDeliveryService.send_text()         │
│                → Twilio REST API (if env vars set)       │
│                  OR print() to stdout                    │
│            → writes DeliveryLog row                      │
│            → writes TriggeredUser.DeliverySucceeded      │
└──────────────────────────────────────────────────────────┘

Overlay Tables (created by this system via Alembic):
  AI_ChatBot_EngagementEvents    (append-only)
  AI_ChatBot_DeliveryLog         (append-only)
  AI_ChatBot_Directives          (CRUD)
  AI_ChatBot_BehaviorFingerprints (write)
  AI_ChatBot_DiscoveredKPIs      (write)
  AI_ChatBot_GeneratedInsights   (write)
  AI_ChatBot_StudentResponses    (append-only)
```

---

## PART C — ACTUAL EXECUTION FLOW (Single Trigger Cycle)

```
1. External system writes a row to AI_ChatBot_TriggeredUsers with Completed=0
   (or POST /ai/trigger/process is called by an external webhook)

2. Trigger Worker polls: SELECT WHERE Completed=0

3. For each pending CBM_ID:
   a. Read TriggerRule from DB (gets message templates, KPI thresholds)
   b. Read TriggerData for the student (gets KPI values)
   c. TriggerEvaluator.evaluate() runs:
      - reads student KPI value (e.g., LastLoginDays)
      - compares against TriggerLow/TriggerHigh thresholds
      - returns "Low" | "High" | "Unknown" | "None"
      - selects ChatGPTPromptLowTrigger or ChatGPTPromptHighTrigger
        (these are pre-written strings stored in the DB, not AI output)
   d. UPDATE TriggeredUsers SET Completed=1 WHERE CBM_ID=? AND Completed=0
      RETURNING CBM_ID  — atomic claim prevents duplicate sends
   e. If claim succeeded:
      - AuditLogService writes to AI_ChatBot_AuditLog
      - EngagementTrackerService writes to AI_ChatBot_EngagementEvents
      - OutboundDeliveryService.send_text():
          - reads student phone/email from TriggerData
          - calls Twilio REST API (if TWILIO_* env vars set)
          - OR: prints message to stdout (dev mode)
      - Writes DeliveryLog row (success/failure, provider_id)
      - Writes TriggeredUser.DeliverySucceeded = True/False

4. Student replies via SMS/WhatsApp → inbound webhook (not yet implemented)
   MentorMessageService.handle() receives the message:
   - Returns hardcoded "Your message has been received..." string
   - Logs ChatBotAuditLog + EngagementEvent
   - Does NOT call Claude API or any LLM
```

---

## PART D — ARCHITECTURAL DELUSION INVENTORY

### Delusion 1: "Event-Driven Orchestration"
**What it claims:** Asynchronous event bus with governed propagation, correlation IDs, parent event chains, payload versioning, governance context on every event.
**What exists:** `SELECT WHERE Completed=0` polling loop run manually or on a cron schedule.
**Real implementation cost:** 4–6 weeks (queue infrastructure + schema + producers + consumers + dead-letter handling).
**Recommendation:** STUB — document the polling pattern as the current implementation. Add a queue in Phase 3 when volume requires it. Do not describe it as "event-driven" until then.

### Delusion 2: "Replay-Safe [Everything]"
**What it claims:** Every operation is replayable; historical state can be reconstructed by re-executing events.
**What exists:** Append-only audit tables (AuditLog, EngagementEvents, DeliveryLog) — these are forensic records, not replay sources. Twilio SMS delivery cannot be replayed. The `UPDATE Completed=1` claim operation cannot be replayed (it would find Completed=1 and fail silently).
**Real implementation cost:** 8–12 weeks (event store, versioned schemas, deterministic handlers, snapshot mechanism, replay executor).
**Recommendation:** REMOVE from vocabulary. Replace with "forensically auditable." Build event sourcing only if an explicit operational requirement demands it.

### Delusion 3: "AI-Powered Mentor Intelligence"
**What it claims:** LLM-driven reasoning, personalized AI communication, intelligent agent responses.
**What exists:** Database column retrieval (`ChatGPTPromptLowTrigger` VARCHAR field) and Python keyword matching in `generate_explanation()`.
**Real implementation cost:** 1–2 weeks to integrate `anthropic` SDK into `MentorMessageService` for real inference.
**Recommendation:** KEEP the architecture, IMPLEMENT the real AI. Label the current behavior as "template-based" until LLM calls are added.

### Delusion 4: "Multi-Agent Debate System"
**What it claims:** Multiple AI agents challenging proposals, structured debates, Lead Architect Agent arbitrating conflicts, agent lifecycle management.
**What exists:** `agents/__init__.py` (empty), `agents/README.md` (placeholder).
**Real implementation cost:** 6–12 weeks (agent framework, structured debate protocol, arbitration logic, agent state persistence).
**Recommendation:** DEFER to Phase 9. This is aspirational architecture.

### Delusion 5: "Governance Approval Engine"
**What it claims:** Approval-gated execution, policy enforcement engine, human escalation routing, rollback orchestration.
**What exists:** Zero. No table, no class, no route, no field.
**Real implementation cost:** 2–3 weeks (table, service, API route, minimal UI).
**Recommendation:** BUILD NOW. This is the most critical unimplemented requirement.

### Delusion 6: "24 Named Services" (GovernanceReviewService, SimulationService, etc.)
**What it claims:** A full service mesh with ownership, governance contracts, replay compatibility, environment routing.
**What exists:** 11 implemented Python service classes (see PART F below).
**Real implementation cost:** Varies; most are legitimate future services that require 1–4 weeks each.
**Recommendation:** REMOVE from current architecture diagrams. Add to roadmap with phase assignments.

### Delusion 7: "RBAC with Scoped Permissions"
**What it claims:** Role-based access control, least-privilege agents, scoped access, time-bound authorization.
**What exists:** Single static `API_KEY` env var with string comparison (`config/auth.py:17–24`).
**Real implementation cost:** 1–2 weeks (JWT-based auth + role enum + scope decorator).
**Recommendation:** DEFER for MVP. Document the current auth as "single-tenant API key" and upgrade to JWT when multi-user access is needed.

### Delusion 8: "Observation Layer / Database Intelligence"
**What it claims:** Continuous SQL Server monitoring, query plan analysis, trigger dependency mapping, entropy scoring.
**What exists:** `execution/db_reflect.py` — reads SQL Server system catalog (`information_schema`, `sys.tables`). Not wired into any service. Not scheduled. Not persisted.
**Real implementation cost:** 3–4 weeks (DMV queries, telemetry storage, scheduled collection, API endpoints).
**Recommendation:** BUILD in Phase 1. This is the actual unique value proposition.

---

## PART E — WHAT ACTUALLY EXISTS (Canonical Service Map)

### Implemented and Working
| Service/Class | File | Purpose | AI? |
|---|---|---|---|
| `TriggerEvaluator` | `services/trigger_processing_service.py:47` | Pure threshold evaluation | No |
| `DbTriggerProcessingService` | `services/trigger_processing_service.py:198` | DB-backed trigger evaluation + write | No |
| `TriggerProcessingService` | `services/trigger_processing_service.py:186` | Stub (tests only) | No |
| `MentorMessageService` | `services/mentor_message_service.py:13` | Orchestrate inbound/outbound | No (hardcoded string) |
| `OutboundDeliveryService` | `services/outbound_delivery_service.py:15` | Twilio/SMTP delivery | No |
| `EngagementTrackerService` | `services/engagement_tracker_service.py:9` | Append EngagementEvent | No |
| `AuditLogService` | `services/audit_log_service.py` | Append ChatBotAuditLog | No |
| `DirectiveService` | `services/directive_service.py` | Directive CRUD | No |
| `StudentStatusFetcher` | `services/student_status_fetcher.py` | Read student status | No |
| `FingerprintEvaluator` | `core/fingerprint/evaluator.py:6` | Threshold pattern matching | No (rules only) |
| `KPIDiscoveryAnalyzer` | `core/kpi_discovery/analyzer.py:9` | Hardcoded avg_logins | No |
| `InsightGenerator` | `core/insight/generator.py:7` | KPI+fingerprint → insight | No (templates) |
| `generate_explanation` | `skills/insight_explainer/skill.py:78` | Keyword → template string | No |
| `process_pending_triggers` | `services/worker/trigger_worker.py:18` | Poll and dispatch | No |

### Needed But Not Yet Built
| Service | Purpose | Priority |
|---|---|---|
| `GovernanceApprovalService` | Approval request lifecycle | P0 — blocks spec compliance |
| `ObservationService` | SQL Server telemetry collection | P1 |
| `TriggerDependencyMapper` | Trace trigger→proc→queue chains | P2 |
| `AnthropicMentorService` | Real LLM inference for messages | P1 — needed for "AI" claims |

---

## PART F — CANONICAL BOUNDED CONTEXTS

### BC-1: Student Engagement (EXISTS)
**Scope:** Receive trigger events, evaluate rules, dispatch messages, track responses.
**Entities:** TriggerData, TriggerRule, TriggeredUser, ConversationState, EngagementEvent, StudentResponse
**Services:** TriggerEvaluator, DbTriggerProcessingService, MentorMessageService, OutboundDeliveryService, EngagementTrackerService
**Status:** Functional (messages are template-based; upgrade to LLM is the next step)

### BC-2: Audit (EXISTS)
**Scope:** Append-only record of every action, message, and delivery.
**Entities:** ChatBotAuditLog, DeliveryLog, EngagementEvent
**Services:** AuditLogService, EngagementTrackerService
**Status:** Functional. This is the "replay" capability: forensic reconstruction only.

### BC-3: Intelligence (PARTIAL)
**Scope:** Behavioral fingerprinting, KPI discovery, insight generation.
**Entities:** BehaviorFingerprint, DiscoveredKPI, GeneratedInsight
**Services:** FingerprintEvaluator, KPIDiscoveryAnalyzer, InsightGenerator
**Status:** Rule-based. No LLM. KPIDiscovery hardcoded. Needs LLM integration.

### BC-4: Governance (MISSING)
**Scope:** Approval-gated execution, policy enforcement, human oversight.
**Entities:** ApprovalRequest (not built), ExecutionRecord (not built)
**Services:** GovernanceApprovalService (not built)
**Status:** Zero implementation. This is the critical gap.

### BC-5: Database Intelligence (EMBRYONIC)
**Scope:** SQL Server observation, dependency mapping, optimization proposals.
**Entities:** QueryTelemetry (not built), TriggerDependencyNode (not built)
**Services:** db_reflect.py (partial start, not wired)
**Status:** 5% complete. This is the unique value proposition of the platform.

### BC-6: Directives (EXISTS)
**Scope:** Versioned operational SOP management.
**Entities:** Directive
**Services:** DirectiveService
**Status:** Functional.

---

## PART G — RECOMMENDED CANONICAL ARCHITECTURE (MVP)

```
┌────────────────── EXTERNAL BOUNDARY ──────────────────┐
│  SQL Server (production, read-only for core tables)    │
│  Twilio API (SMS/WhatsApp delivery)                    │
│  SMTP (email delivery)                                 │
│  Claude API (LLM inference — to be wired)              │
└───────────────────────┬───────────────────────────────┘
                        │
┌───────────────────────▼───────────────────────────────┐
│               FastAPI Application                      │
│                                                        │
│  /ai/trigger/process  → TriggerProcessingService      │
│  /ai/mentor/message   → MentorMessageService          │
│  /api/directives      → DirectiveService              │
│  /api/fingerprint     → FingerprintService            │
│  /api/insight         → InsightService                │
│  /api/kpi             → KPIService                    │
│  /api/governance      → GovernanceService [BUILD]     │
│  /api/admin           → AdminDashboard [BUILD]        │
│                                                        │
│  Auth: API Key (current) → JWT + roles [FUTURE]       │
└───────────────────────┬───────────────────────────────┘
                        │
┌───────────────────────▼───────────────────────────────┐
│            Service Layer                               │
│                                                        │
│  TriggerEvaluator      (pure, no I/O)                 │
│  DbTriggerProcessingService                           │
│  MentorMessageService  [+ LLM integration needed]     │
│  OutboundDeliveryService                              │
│  EngagementTrackerService                             │
│  AuditLogService                                      │
│  DirectiveService                                     │
│  GovernanceApprovalService  [BUILD — Sprint 1]        │
│  ObservationService         [BUILD — Sprint 2]        │
└───────────────────────┬───────────────────────────────┘
                        │
┌───────────────────────▼───────────────────────────────┐
│            Data Layer (SQLAlchemy 2.0)                 │
│                                                        │
│  SQL Server:  TriggerData, TriggerRule, TriggeredUser  │
│               ConversationState, ChatBotAuditLog       │
│                                                        │
│  Overlay DB:  EngagementEvents, DeliveryLog           │
│               Directives, BehaviorFingerprints         │
│               DiscoveredKPIs, GeneratedInsights        │
│               StudentResponses                         │
│               ApprovalRequests [BUILD]                 │
└────────────────────────────────────────────────────────┘
```

---

## PART H — CANONICAL VOCABULARY TABLE

All duplicated doctrine terminology reduced to canonical engineering terms.

| Doctrine Term(s) | Canonical Term | Engineering Reality |
|---|---|---|
| "Constitutional Closure/Preservation/Authorization/Covenant/Codex/Charter/Manifesto/Treatise/Compendium/Tome/Canon/Index/Registry/Archive" (42 variants) | **Governance Policy** | CLAUDE.md + spec + one governance doc |
| "Eternal Species Continuity / Civilizational Resilience / Humanity Preservation / Trans-civilizational Memory / Post-humanity Continuity" | **System Continuity** | 99.9% uptime SLO |
| "Eternal [X] Runtime Engine" | **Service class** | A Python class |
| "Replay-safe [anything]" | **Auditable** | Append-only log tables |
| "Institutional Lineage / Organizational Ancestry / Constitutional Heritage" | **Audit Log** | AI_ChatBot_AuditLog table |
| "Species Survivability" | **System Availability** | Uptime metric |
| "Human Authority Preservation" | **Human-in-the-Loop Approval** | GovernanceApprovalService (not built) |
| "Explainability Continuity" | **Recommendation Rationale** | `explanation` field on GeneratedInsight |
| "Escalation Continuity" | **Alert Routing** | PagerDuty / email alert |
| "Confidence Governance" | **Confidence Score Threshold** | `confidence > 0.7` check in InsightGenerator |
| "Environment Isolation" | **Dev/Staging/Production Separation** | MSSQL_CONFIGURED flag + env vars |
| "Governance-Gated Execution" | **Approval-Required Execution** | GovernanceApprovalService (not built) |
| "Eternal Closure Governance Coordinator" | **GovernanceService** | Does not exist |
| "Drift Governance Runtime" | **Configuration Drift Detector** | Does not exist |
| "Institutional Stability Runtime" | **Health Check Service** | Does not exist |
| "Containment Governance Router" | **Circuit Breaker** | Does not exist |
| "Constitutional Governance Engine" | **Policy Validator** | Does not exist |
| "Replay Governance Coordinator" | **Audit Query API** | Does not exist |
| "Observation Constitutional Operations" | **Metrics Collection** | db_reflect.py (partial) |
| "Agent Debate System" | **Multi-Agent LLM Orchestration** | Does not exist |
| "Rollback Orchestration" | **Undo/Rollback Mechanism** | Does not exist |
| "Simulation Service" | **Execution Dry-Run** | Does not exist |
| "Fairness Governance Engine" | **Bias Checker** | Does not exist |
