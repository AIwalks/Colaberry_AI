# MVP RECOMMENDATION — MAXIMUM RIGOR EDITION
**Colaberry Sentinel OS | Date: 2026-05-07**

---

## PART A — COMPLETE CONCEPT CLASSIFICATION

Every concept found across all documentation, classified by implementability and MVP necessity.

### REQUIRED FOR MVP — NOT YET BUILT

| Concept | Why Required | Estimated Effort | Where to Build |
|---|---|---|---|
| Approval-gated execution | Core spec requirement FR-EXEC-001; the system currently acts autonomously | 2–3 weeks | `services/governance_approval_service.py` + migration + route |
| Human approval UI | Without UI, approval service is unusable | 1 week | React admin panel or FastAPI HTML page |
| Real LLM inference in MentorMessage | Currently returns hardcoded string; "AI" claims require actual AI | 1 week | Wire `anthropic` SDK into `MentorMessageService` |
| SQL Server observation queries | Core value proposition (DB intelligence) doesn't work without telemetry | 3–4 weeks | `services/observation_service.py` |
| Trigger dependency mapper | Need to understand what triggers what before recommending changes | 2–3 weeks | `services/dependency_mapper.py` |
| Inbound message handler (real) | Student replies currently return hardcoded constant | 1–2 weeks | Replace constant in `MentorMessageService.handle()` |
| ApprovalRequests table | Required by GovernanceApprovalService | 0.5 weeks | Alembic migration 0010 |

### REQUIRED FOR MVP — ALREADY BUILT ✓

| Capability | File | Status |
|---|---|---|
| API with authentication | `app/main.py`, `config/auth.py` | ✓ Works |
| Trigger evaluation (threshold) | `services/trigger_processing_service.py` | ✓ Works |
| Trigger worker (polling) | `services/worker/trigger_worker.py` | ✓ Works |
| Outbound delivery (Twilio/SMTP) | `services/outbound_delivery_service.py` | ✓ Works (requires env vars) |
| Engagement event logging | `services/engagement_tracker_service.py` | ✓ Works |
| Message audit log | `services/audit_log_service.py` | ✓ Works |
| Student response tracking | `services/models.py:StudentResponse` | ✓ Schema exists |
| Delivery success tracking | `TriggeredUser.DeliverySucceeded` | ✓ Works |
| Directive management | `services/directive_service.py` | ✓ Works |
| Alembic migrations (9) | `alembic/versions/` | ✓ Works |
| Dev/prod DB switching | `config/database.py:MSSQL_CONFIGURED` | ✓ Works |
| Test suite | `tests/` | ✓ 25+ tests |
| Behavior fingerprinting (rules) | `core/fingerprint/evaluator.py` | ✓ Works (no LLM) |

### FUTURE ENTERPRISE FEATURE — DO NOT BUILD NOW

| Concept | Why Future | Earliest Phase |
|---|---|---|
| Event sourcing / replay infrastructure | Requires 8–12 weeks; audit logs are sufficient for MVP forensics | Phase 7+ |
| Multi-agent debate system | Requires stable single-agent baseline first; 6–12 weeks | Phase 9 |
| Agent lifecycle management | No agents exist to manage | Phase 9 |
| Rollback orchestration engine | No governed execution exists to roll back | Phase 7 |
| Query plan simulation | Requires weeks of SQL Server observation data first | Phase 6 |
| Concurrency simulation | Complex; low MVP value | Phase 6 |
| Longitudinal intelligence | Requires 90+ days production data | Phase 10 |
| Multi-campus governance | No second campus exists | Phase 10+ |
| Bias detection engine | Requires labeled fairness data (not yet defined) | Phase 8+ |
| Service mesh architecture | No mesh needed at current scale | Phase 5+ |
| Time-bound authorization | Single-tenant API key is sufficient for now | Phase 4 |
| Governance review board software | Run as human process first; software later | Phase 4 |
| Mandrill email integration | SMTP works; Mandrill adds complexity | Phase 3 |
| Voice delivery | Low-value add; high Twilio cost | Phase 5 |

### CEREMONIAL / DOCUMENTATION ONLY — NO CODE EVER NEEDED

| Doctrine Concept | Reality | Action |
|---|---|---|
| "Constitutional Closure Governance" | = CLAUDE.md + governance_policy.md | ARCHIVE — already exists in better form |
| "Species Continuity Architecture" | = System uptime | DELETE — not an engineering concept |
| "Eternal Institutional Lineage" | = Audit log queries | DELETE — already implemented |
| "Trans-civilizational Replay Safety" | = Audit tables | DELETE — meaningless at this scope |
| "Constitutional Humanity Preservation" | = Data protection + GDPR compliance | REPLACE with concrete compliance requirements |
| "Governance Closure Classification Framework" | = Severity: Low/Medium/High/Critical | DELETE — 6 categories → 4 severity levels |
| "Eternal Species Continuity Sustainability" | = System SLA | DELETE — describe as 99.9% uptime SLA |
| "Perpetual Human Authority" | = Human approval gate | REPLACE with GovernanceApprovalService |
| "42 Supreme Constitutional Documents" | = 1 governance policy doc | DELETE 41, keep 1 |

### NON-IMPLEMENTABLE (as written)

| Doctrine Claim | Why Impossible |
|---|---|
| "Infinite replay reconstructability" | Storage is finite; "infinite" is not an engineering property |
| "Eternal constitutional humanity closure" | "Eternal" systems do not exist; systems have end-of-life |
| "Post-humanity replay-safe continuity" | A system that outlasts humanity cannot be tested or maintained |
| "Species-level institutional survivability" | The governing body (humans) is the scope; "species" is not |
| "Deterministic eternal humanity continuity" | "Eternal" + "deterministic" is a contradiction in distributed systems |
| "Perpetual governance cycle" | All cycles terminate; governance has review cadences, not perpetual loops |
| "CONSTITUTIONAL_CONSTITUTIONAL_CLOSURE" | A category that governs itself is logically undefined |

### OVER-ENGINEERED — SIMPLIFY OR REMOVE

| Over-Engineering | Simpler Alternative |
|---|---|
| 42 "supreme" constitutional docs | 1 `governance_policy.md` |
| "Universal Constitutional Governance Model" (9 mandatory attributes per workflow) | A PR checklist with 5 items |
| "Closure Classification Framework" (6 categories) | Severity: low / medium / high / critical |
| "Replay Compatibility Framework" (separate section in every doc) | One sentence: "All actions log to append-only tables" |
| "Constitutional Failure Containment Framework" | `try/except + log + alert` |
| "Eternal Constitutional Oversight Framework" | Quarterly governance review meeting |
| "Species Continuity Sustainability Governance" | System SLA agreement |

---

## PART B — MINIMUM VIABLE ARCHITECTURE (EXECUTABLE SPEC)

### Minimum Services

```python
# What must exist for MVP (with file targets)

services/
  trigger_processing_service.py       # EXISTS — TriggerEvaluator, DbTriggerProcessingService
  mentor_message_service.py           # EXISTS — needs LLM wiring
  outbound_delivery_service.py        # EXISTS — Twilio works
  engagement_tracker_service.py       # EXISTS
  audit_log_service.py                # EXISTS
  directive_service.py                # EXISTS
  student_status_fetcher.py           # EXISTS
  governance_approval_service.py      # MISSING — P0 BUILD

core/
  fingerprint/evaluator.py            # EXISTS (rule-based, upgrade later)
  insight/generator.py                # EXISTS (template-based, upgrade later)
  kpi_discovery/analyzer.py           # EXISTS (hardcoded, upgrade later)

workers/
  trigger_worker.py                   # EXISTS
```

### Minimum Database Schema

```sql
-- EXISTING (production, read-only)
AI_ChatBot_TriggerData
AI_ChatBot_TriggerRules

-- EXISTING (overlay, managed by Alembic)
AI_ChatBot_TriggeredUsers         -- add ApprovalRequired bit column
AI_ChatBot_ConversationState
AI_ChatBot_AuditLog
AI_ChatBot_EngagementEvents
AI_ChatBot_DeliveryLog
AI_ChatBot_Directives
AI_ChatBot_BehaviorFingerprints
AI_ChatBot_DiscoveredKPIs
AI_ChatBot_GeneratedInsights
AI_ChatBot_StudentResponses

-- MISSING (must add for governance MVP)
AI_ChatBot_ApprovalRequests       -- migration 0010
  id INTEGER PK
  action_type VARCHAR(50) NOT NULL    -- 'trigger_dispatch', 'schema_change', etc.
  scope_json TEXT NOT NULL            -- what will happen
  rollback_json TEXT                  -- how to undo
  status VARCHAR(20) DEFAULT 'pending'  -- pending/approved/denied
  requested_by VARCHAR(100)
  approved_by VARCHAR(100)
  denial_reason TEXT
  requested_at DATETIME NOT NULL
  decided_at DATETIME
  cbm_id INTEGER                      -- FK-style to TriggeredUser
```

### Minimum Governance Implementation

Not a "Constitutional Governance Engine". Just this:

```python
# services/governance_approval_service.py

class GovernanceApprovalService:
    def request_approval(self, action_type: str, scope: dict,
                         rollback: dict | None, requested_by: str) -> int:
        """Insert ApprovalRequest row, return its ID."""

    def approve(self, approval_id: int, approver: str) -> None:
        """Set status='approved', decided_at=now, approved_by=approver."""

    def deny(self, approval_id: int, approver: str, reason: str) -> None:
        """Set status='denied', decided_at=now, denial_reason=reason."""

    def require_approved(self, approval_id: int) -> None:
        """Raise GovernanceError if status != 'approved'."""

    def list_pending(self) -> list[dict]:
        """Return all rows where status='pending'."""
```

Gate check in DbTriggerProcessingService for severity >= 3:
```python
if rule.Severity >= 3:
    approval_id = GovernanceApprovalService().request_approval(...)
    raise PendingApprovalError(approval_id)
# For severity < 3, proceed immediately (low-risk auto-approve)
```

### Minimum Audit Capability

Already achieved. The existing append-only tables provide complete forensic reconstruction. No additional infrastructure needed.

### Minimum AI Capability

Replace the hardcoded string in `MentorMessageService.handle()` and the template lookup in `process_trigger()` with:

```python
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

def generate_mentor_message(student_context: dict, trigger_context: dict) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system="You are a supportive mentor...",
        messages=[{"role": "user", "content": build_prompt(student_context, trigger_context)}],
    )
    return response.content[0].text
```

This is 1–2 weeks of work. Until this is done, the system is not "AI-powered" — it is template-powered.

### Minimum Security Model

Current: `API_KEY` header string comparison. Adequate for MVP.
Keep for now. Document it honestly. Add JWT with roles in Phase 4.

### Minimum Observability

Current: `print()` statements. Adequate for development.
For MVP production: structured logging via `config/logging.py`. Add `LOG_LEVEL` env var.
Actual monitoring: delivery failure rate from `DeliveryLog WHERE success=False`.

### Minimum Deployment

Current: `uvicorn app.main:app`. Adequate.
For production: Docker container + MSSQL_DATABASE_URL env + TWILIO_* env + ANTHROPIC_API_KEY env + API_KEY env.

---

## PART C — MVP NON-GOALS (EXPLICIT DO-NOT-BUILD LIST)

1. **Event sourcing** — The audit log is sufficient. Building event sourcing before it is required wastes 8–12 weeks.

2. **Replay executor** — There is no operational scenario requiring state reconstruction from events. If this changes, evaluate then.

3. **Multi-agent debate system** — Building agent orchestration before the single-agent baseline is LLM-powered is incoherent sequencing.

4. **Rollback orchestration** — There is nothing to roll back. The system creates additive overlay records. The rollback is "delete the overlay record."

5. **Service mesh / distributed services** — The system is a monolith and should stay that way until throughput demands separation.

6. **Governance review board software** — Run the governance review as a meeting. Build the software when the meeting produces repeatable process artifacts to automate.

7. **Any new constitutional doctrine files** — The existing CLAUDE.md and spec cover governance adequately. No additional doctrine is needed.

8. **Mandrill / Voice integrations** — SMS and email work. Add channels only when a specific student population requires them.

9. **Bias detection engine** — Requires a defined fairness metric, labeled examples, and a test population. None exist.

10. **Longitudinal intelligence** — Requires 90+ days of production data to have statistical validity.

---

## PART D — WHAT WOULD KILL THE MVP

Listed in declining danger:

1. **Continuing to write doctrine files instead of building the approval gate.** The governance layer is 0% implemented. Every hour spent on doctrine is an hour not spent on the critical path.

2. **Treating the current "AI" as real LLM intelligence.** When someone expects AI-personalized messages and receives a database VARCHAR, trust is destroyed.

3. **Not having a production DB connection.** The system falls back to SQLite silently. If `MSSQL_DATABASE_URL` is not configured in production, `process_pending_triggers()` returns 0 and nothing happens. There is no alert.

4. **No rate limiting on Twilio sends.** The trigger worker sends one message per pending trigger with no throttle. A large batch of new students could trigger hundreds of simultaneous Twilio calls, hitting rate limits or generating unexpected charges.

5. **Thread ID persistence gaps.** `StudentResponse.match_method` favors "thread_id" matching, but if thread_id is not correctly propagated through the outbound→inbound cycle, all responses fall back to "time_proximity" matching, which is unreliable.

6. **The `KPIDiscoveryAnalyzer` is hardcoded.** It returns one KPI (`avg_logins`) regardless of input. Any downstream insight that claims to "discover" KPIs is lying.

7. **No error alerting.** `process_pending_triggers()` swallows all exceptions per trigger (`except Exception: continue`). If every trigger fails, the system logs nothing to any monitoring system. Failures are invisible.
