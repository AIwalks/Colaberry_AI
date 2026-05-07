# IMPLEMENTATION SEQUENCE — MAXIMUM RIGOR EDITION
**Colaberry Sentinel OS | Date: 2026-05-07**

---

## GROUND STATE: WHAT IS ACTUALLY RUNNING RIGHT NOW

```
✓ FastAPI app boots (requires API_KEY env var)
✓ POST /ai/trigger/process → evaluates rules, writes TriggeredUser
✓ POST /ai/mentor/message → returns hardcoded string, logs audit
✓ Trigger worker polls TriggeredUser WHERE Completed=0
✓ OutboundDeliveryService sends via Twilio (if TWILIO_* set, else prints)
✓ Email delivery via SMTP (if EMAIL_* set)
✓ EngagementEvent logged per action
✓ DeliveryLog written per delivery attempt
✓ ChatBotAuditLog written per message
✓ DeliverySucceeded written back to TriggeredUser
✓ BehaviorFingerprint evaluation (threshold-based, no LLM)
✓ InsightGenerator (template-based, no LLM)
✓ KPIDiscoveryAnalyzer (hardcoded avg_logins, no real discovery)
✓ DirectiveService (DB CRUD)
✓ Alembic migrations 0001–0007 applied; 0008–0009 untracked (not committed)
✓ SQLite fallback when MSSQL not configured
✓ 25+ unit tests passing
✓ React frontend (shell only — App.tsx has no real UI)

✗ No LLM inference in any production path
✗ No approval gate
✗ No governance service
✗ No observation layer
✗ No admin UI
✗ No inbound response matching logic (schema exists, no handler)
✗ No error alerting
✗ No production deployment
```

---

## SPRINT 0 — TECHNICAL DEBT CLEANUP (1 WEEK)
**Goal: Make the ground state honest and stable before adding features.**

### 0.1 Commit Untracked Migrations
```
git add alembic/versions/0008_add_thread_id_to_engagement_events.py
git add alembic/versions/0009_add_student_responses_table.py
git commit -m "feat: commit untracked Alembic migrations 0008 and 0009"
alembic upgrade head  # run against dev DB to verify
```

### 0.2 Create EventType Constants Module
```python
# services/event_types.py
class EventType:
    TRIGGER_EVALUATED  = "trigger_evaluated"
    TRIGGER_DISPATCHED = "trigger_dispatched"
    INCOMING_MESSAGE   = "incoming_message"
    MESSAGE_DELIVERED  = "message_delivered"
    MESSAGE_FAILED     = "message_failed"
    RESPONSE_MATCHED   = "response_matched"
    INSIGHT_GENERATED  = "insight_generated"
    FINGERPRINT_UPDATED = "fingerprint_updated"
```
Replace string literals in `trigger_processing_service.py:276`, `mentor_message_service.py:60,142` with `EventType.*`.

### 0.3 Fix KPIDiscoveryAnalyzer Honesty
`core/kpi_discovery/analyzer.py` currently returns one hardcoded KPI (`avg_logins`) regardless of input fingerprints. Add a docstring: "Currently returns a single hardcoded KPI. Real discovery requires LLM integration." Until LLM is wired, callers should treat discovery output as illustrative only.

### 0.4 Add Startup Health Check
```python
# In app/main.py lifespan():
if not os.environ.get("MSSQL_DATABASE_URL"):
    print("[WARNING] MSSQL_DATABASE_URL not set. Running against SQLite. "
          "No production data will be processed.")
```

### 0.5 Add Worker Failure Alerting
`trigger_worker.py:44–46` currently swallows all exceptions with `continue`. Add:
```python
except Exception as e:
    print(f"[ERROR] Failed processing trigger {cbm_id}: {e}")
    # TODO Sprint 1: post to alerting channel (email/Slack)
    failed_count += 1
    continue
```

**Sprint 0 Exit: All tests still pass. Untracked migrations committed. String literals replaced with constants.**

---

## SPRINT 1 — GOVERNANCE FOUNDATION (2–3 WEEKS)
**Goal: Make the system compliant with FR-EXEC-001 (approval-gated execution).**
**This is the most important sprint. Everything else is secondary.**

### 1.1 Alembic Migration 0010: ApprovalRequests Table
```python
# alembic/versions/0010_add_approval_requests_table.py
# Schema defined in GOVERNANCE_MODEL.md Part C, Step 1
```

### 1.2 ApprovalRequest ORM Model
```python
# Add to services/models.py after StudentResponse:

class ApprovalRequest(Base):
    __tablename__ = "AI_ChatBot_ApprovalRequests"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    action_type    = Column(String(50), nullable=False)
    scope_json     = Column(Text, nullable=False)
    rollback_json  = Column(Text, nullable=True)
    status         = Column(String(20), nullable=False, default="pending")
    requested_by   = Column(String(100), nullable=True)
    approved_by    = Column(String(100), nullable=True)
    denial_reason  = Column(Text, nullable=True)
    requested_at   = Column(DateTime, nullable=False)
    decided_at     = Column(DateTime, nullable=True)
    cbm_id         = Column(Integer, nullable=True, index=True)
    expires_at     = Column(DateTime, nullable=True)
```

### 1.3 GovernanceApprovalService
```
services/governance_approval_service.py
  GovernanceError
  PendingApprovalError(approval_id)
  GovernanceApprovalService.request_approval()
  GovernanceApprovalService.approve()
  GovernanceApprovalService.deny()
  GovernanceApprovalService.require_approved()
  GovernanceApprovalService.list_pending()
```
Full implementation in GOVERNANCE_MODEL.md Part C, Step 2.

### 1.4 Gate in DbTriggerProcessingService
Severity >= 3 triggers must request approval before creating TriggeredUser.
Severity < 3 auto-proceed.
Implementation in GOVERNANCE_MODEL.md Part C, Step 3.

### 1.5 Governance API Routes
```
GET  /api/governance/pending           → list pending approvals
POST /api/governance/approve/{id}      → approve
POST /api/governance/deny/{id}         → deny
GET  /api/audit/trigger/{cbm_id}       → forensic reconstruction endpoint
```

### 1.6 Minimal Admin HTML Page
`GET /admin` returns an HTML page listing pending approvals with Approve/Deny buttons.
Can be rendered by Jinja2 templates via FastAPI. Does not require React.

### 1.7 Tests
```
tests/unit/test_governance_approval_service.py:
  test_request_approval_creates_pending_row()
  test_approve_changes_status()
  test_deny_changes_status_with_reason()
  test_require_approved_raises_on_pending()
  test_require_approved_raises_on_denied()
  test_require_approved_passes_on_approved()
  test_high_severity_trigger_creates_approval_request()
  test_low_severity_trigger_bypasses_approval()
  test_cannot_approve_nonexistent_request()
```

**Sprint 1 Exit: High-severity triggers are blocked until a human approves. Audit trail includes all approval decisions. Tests confirm bypass is impossible.**

---

## SPRINT 2 — REAL LLM INTEGRATION (1–2 WEEKS)
**Goal: Replace template strings with real Claude API inference.**

### 2.1 Wire Anthropic SDK into MentorMessageService

Current: `message_text = rule.ChatGPTPromptLowTrigger` (reads VARCHAR from DB)
Target: Use the stored prompt as a system prompt, ask Claude to personalize for the student.

```python
# services/mentor_message_service.py
import anthropic

def _generate_ai_message(self, prompt_template: str, student: TriggerData) -> str:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=prompt_template,
        messages=[{
            "role": "user",
            "content": f"Generate a personalized mentor message for {student.FirstName}. "
                       f"Context: {student.ActiveStatus}, days since login: {student.LastLoginDays}."
        }]
    )
    return response.content[0].text
```

Add `ANTHROPIC_API_KEY` to required env vars. Add to startup validation in `lifespan()`.

### 2.2 Replace Hardcoded Inbound Response
```python
# Current (mentor_message_service.py:39–41):
"text": "Your message has been received and logged. A mentor will follow up shortly."

# Target: Call Claude to generate a contextual acknowledgment
def _generate_inbound_ack(self, student_message: str, student_id: str) -> str:
    # brief Claude call acknowledging the message and asking a follow-up question
```

### 2.3 Wire LLM into InsightGenerator
Replace `generate_explanation()` keyword-matching templates with a Claude call that generates a real explanation given the insight title and entity context.

### 2.4 Fallback Handling
If `ANTHROPIC_API_KEY` is not set or Claude returns an error: fall back to the existing template string. Log a warning. Never fail silently.

### 2.5 Tests
```
tests/unit/test_mentor_message_llm.py:
  test_uses_template_fallback_when_anthropic_not_configured()
  test_llm_message_stored_in_delivery_log()

tests/integration/test_end_to_end_with_claude.py:  (requires ANTHROPIC_API_KEY)
  test_trigger_generates_personalized_message()
```

**Sprint 2 Exit: System makes real Claude API calls for outbound messages. Falls back gracefully if API unavailable. "AI-powered" claim is now true.**

---

## SPRINT 3 — OBSERVATION LAYER (3–4 WEEKS)
**Goal: Implement Phase 1 of the implementation roadmap — SQL Server observation.**

### 3.1 ObservationService
```python
# services/observation_service.py
class ObservationService:
    def collect_table_sizes(self) -> list[dict]:
        """Query sys.dm_db_partition_stats for table row counts."""

    def collect_trigger_activity(self) -> list[dict]:
        """Query sys.dm_exec_trigger_stats for trigger execution stats."""

    def collect_index_usage(self) -> list[dict]:
        """Query sys.dm_db_index_usage_stats for index read/write counts."""

    def collect_blocking_chains(self) -> list[dict]:
        """Query sys.dm_exec_requests for active blocking."""

    def collect_recent_queries(self, top_n: int = 20) -> list[dict]:
        """Query sys.dm_exec_query_stats for top expensive queries."""
```

### 3.2 QueryTelemetry Table (Migration 0011)
```sql
CREATE TABLE AI_ChatBot_QueryTelemetry (
    id              INTEGER PK autoincrement,
    collected_at    DATETIME NOT NULL,
    telemetry_type  VARCHAR(50) NOT NULL,  -- table_size/trigger_activity/index_usage/etc.
    object_name     VARCHAR(200),
    metric_json     TEXT NOT NULL,  -- the raw telemetry as JSON
    environment     VARCHAR(20) NOT NULL DEFAULT 'production'
);
```

### 3.3 Scheduled Collection
Add a scheduled trigger to `run_trigger_worker.py` that runs `ObservationService` on a configurable interval (e.g., every 15 minutes).

### 3.4 TriggerDependencyMapper
```python
# services/dependency_mapper.py
class TriggerDependencyMapper:
    def map_trigger_chain(self, trigger_name: str) -> dict:
        """
        Query sys.sql_expression_dependencies and sys.triggers to trace:
        Trigger → references → stored procedures → tables → other triggers
        Returns a dict representing the dependency graph.
        """
```

### 3.5 API Endpoints
```
GET /api/observation/tables          → current table sizes
GET /api/observation/triggers        → trigger activity stats
GET /api/observation/index-usage     → index effectiveness
GET /api/observation/blocking        → current blocking chains
GET /api/observation/dependency/{trigger_name} → trigger dependency graph
```

**Sprint 3 Exit: SQL Server is being observed. Data is persisted. Trigger chains are visible.**

---

## SPRINT 4 — DASHBOARD (1–2 WEEKS)
**Goal: Operational visibility for system operators.**

### React Dashboard (frontend/)
```
Pages:
  /admin/triggers        — recent triggers, pending/completed, delivery rates
  /admin/governance      — pending approvals (Approve/Deny buttons)
  /admin/students/{id}   — student lifecycle reconstruction
  /admin/observation     — SQL Server health metrics
  /admin/insights        — recent generated insights
```

Build with React + fetch() calls to existing API routes. No new backend needed.

**Sprint 4 Exit: A human can see the system state, approve governance requests, and investigate individual students.**

---

## SPRINT 5 — PRODUCTION READINESS (1–2 WEEKS)
**Goal: System can run against real SQL Server in production.**

### 5.1 Environment Validation
Add startup checks for all required env vars:
```python
required = ["API_KEY", "MSSQL_DATABASE_URL", "ANTHROPIC_API_KEY"]
optional_warn = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER",
                 "EMAIL_HOST", "EMAIL_FROM"]
```

### 5.2 Rate Limiting
Add per-student delivery throttle: if a student has received a message in the last X hours, block the next trigger from firing automatically. Check `DeliveryLog WHERE user_id=? AND created_on > ?`.

### 5.3 Structured Logging
Replace all `print()` with `logging.getLogger(__name__)` calls with structured JSON format. Add `LOG_LEVEL` env var.

### 5.4 Health Endpoint
```python
@app.get("/health")
def health():
    return {
        "status": "ok",
        "mssql_configured": MSSQL_CONFIGURED,
        "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "twilio_configured": bool(os.environ.get("TWILIO_ACCOUNT_SID")),
    }
```

### 5.5 Load Test
Run trigger worker against 100 simulated pending triggers. Verify:
- No duplicate sends (atomic claim holds under concurrency)
- All DeliveryLog rows written
- Worker completes in < 60 seconds

**Sprint 5 Exit: System is production-deployable with clear operational visibility.**

---

## PHASES 6–10 (ROADMAP, NOT SPRINT PLANS)

| Phase | When | What |
|---|---|---|
| Phase 6 | Month 4–5 | Execution simulation (dry-run DB changes) |
| Phase 7 | Month 5–6 | Governed additive execution (create overlay indexes/views with approval) |
| Phase 8 | Month 6–8 | Advanced student intelligence (predictive models, bias detection) |
| Phase 9 | Month 8–12 | Multi-agent debate system (requires stable single-agent foundation) |
| Phase 10 | Month 12+ | Longitudinal intelligence (requires 90+ days production data) |

---

## INVARIANTS THAT MUST HOLD ACROSS ALL SPRINTS

```
1. No sprint deploys without all tests passing
2. Every new service has a unit test for the happy path AND at least one failure path
3. Every new DB table goes through Alembic (never manual schema changes)
4. MSSQL_DATABASE_URL must never appear in source code (env var only)
5. Production SQL Server tables (TriggerData, TriggerRules) must never be modified
6. Every sprint ends with an updated PROGRESS.md entry
7. The approval gate must never be disableable via a flag or env var
   (it would be bypassed in dev mode and eventually in prod)
```
