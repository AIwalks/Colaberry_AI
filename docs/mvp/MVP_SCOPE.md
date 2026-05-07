# Colaberry Sentinel OS — MVP Scope
**Last updated: 2026-05-07 | Sprint 0**

---

## The MVP in One Sentence

A governed, AI-powered student engagement system that sends personalized Claude-generated messages when SQL Server KPI thresholds are crossed, with human approval required for high-severity triggers.

---

## What MVP Means Here

MVP is not "minimum viable product as a business." MVP is "minimum set of features that makes the current implementation honest":

1. The system claims to be governed → **build the approval gate** (Sprint 1)
2. The system claims to be AI-powered → **wire real Claude API calls** (Sprint 2)
3. The system claims to have operators → **build a minimal admin UI** (Sprint 4)

Everything else is already working or explicitly deferred.

---

## Sprint Plan (Tactical — Authoritative)

| Sprint | Goal | Key Deliverable | Duration |
|---|---|---|---|
| Sprint 0 | Technical debt cleanup | Migrations committed, EventType enum, honest labels | 1 week |
| Sprint 1 | Governance foundation | Approval gate, ApprovalRequests table, admin page | 2–3 weeks |
| Sprint 2 | Real LLM integration | Claude API in MentorMessageService + InsightGenerator | 1–2 weeks |
| Sprint 3 | Observation layer | ObservationService, QueryTelemetry, DMV queries | 3–4 weeks |
| Sprint 4 | Admin dashboard | 5-page React dashboard | 1–2 weeks |
| Sprint 5 | Production readiness | Rate limiting, structured logging, health endpoint | 1–2 weeks |

**Authoritative sprint details: [audit/IMPLEMENTATION_SEQUENCE.md](../../audit/IMPLEMENTATION_SEQUENCE.md)**

---

## MVP Included

| Feature | Sprint | Notes |
|---|---|---|
| Trigger evaluation (threshold-based) | ✓ Done | Reads KPI against TriggerRules |
| Atomic claim (no duplicate sends) | ✓ Done | UPDATE WHERE Completed=0 RETURNING |
| SMS/WhatsApp via Twilio | ✓ Done | Requires env vars |
| Email via SMTP | ✓ Done | Requires env vars |
| Append-only audit trail | ✓ Done | 4 tables |
| Alembic migrations (additive-only) | Sprint 0 | Commit 0008, 0009; write 0010 |
| EventType constants module | Sprint 0 | Replace string literals |
| Human approval gate (severity ≥ 3) | Sprint 1 | GovernanceApprovalService |
| Admin approval page | Sprint 1 | Jinja2 HTML, no React |
| Claude API message generation | Sprint 2 | Personalized via anthropic SDK |
| Inbound response handler | Sprint 2 | StudentResponse matching |
| SQL Server observation | Sprint 3 | DMV queries, QueryTelemetry |
| Admin dashboard | Sprint 4 | React + existing API |
| Health endpoint | Sprint 5 | /health with config status |

---

## MVP Explicitly Excluded

These are correct decisions, not gaps:

| Excluded | Reason |
|---|---|
| Message queue (Celery, RabbitMQ, Kafka) | Polling worker sufficient at this scale |
| Event sourcing / event store | 8–12 weeks to build; audit tables provide 95% of value |
| Cryptographic audit chains | Overkill for a student chatbot |
| Kubernetes / container orchestration | Docker Compose sufficient until load justifies more |
| RBAC / per-user permissions | Single API key sufficient until multiple operators needed |
| Multi-agent debate system | Phase 9 (requires stable single-agent foundation first) |
| Predictive models / bias detection | Phase 8 (requires 90+ days production data) |
| Production SQL Server mutation | Never — overlay-only by design |

---

## The Four Things That Make This System Real

In priority order:

### 1. Approval Gate (Sprint 1 — blocks FR-EXEC-001 violation)
Every severity ≥ 3 trigger fires without human approval today. That violates the core spec.

### 2. Real Claude API Calls (Sprint 2 — makes "AI-powered" true)
All messages are pre-written VARCHAR strings. No LLM calls exist in any production path.

### 3. Commit Untracked Migrations (Sprint 0 — 30 minutes)
Migrations 0008 and 0009 are untracked. Fresh clone + `alembic upgrade head` = schema mismatch.

### 4. Delete Doctrine Clone Files (Sprint 0 — done)
42+ clone docs blocked every AI assistant from generating real code. Now deleted.

---

## Definition of Done (per CLAUDE.md)

A sprint is not complete unless:
- Relevant unit tests exist and pass
- Behavior-changing logic updates relevant directives
- End-to-end impact is verified where applicable
- No secrets are introduced
- Changes are understandable by a junior developer

---

## Full Scope Analysis

See [audit/MVP_RECOMMENDATION.md](../../audit/MVP_RECOMMENDATION.md) for complete concept classification
(Required / Future / Ceremonial / Non-implementable / Over-engineered).
