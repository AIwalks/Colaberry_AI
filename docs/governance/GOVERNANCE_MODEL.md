# Colaberry Sentinel OS — Governance Model
**Last updated: 2026-05-07 | Sprint 0**

---

## What Governance Means for This System

Governance is not a philosophical framework. For this system it is:

1. A table that records pending action requests (`ApprovalRequests`)
2. A UI that shows pending requests to a human
3. Approve / Deny buttons
4. A check in the execution path that blocks if not approved
5. An audit trail that records who approved what

**Current compliance: 0%.** The system fires all triggers immediately with no approval gate.
**Target sprint: Sprint 1** (2–3 weeks).

---

## Governing Requirements (from spec/01_requirements.md)

```
FR-GOV-001: Humans SHALL retain final authority over:
  - Execution
  - Governance decisions
  - Agent overrides
  - High-risk recommendations

FR-EXEC-001: All executions SHALL require:
  - Proposal linkage
  - Explicit approval
  - Execution request ID
  - Rollback definition
  - Scope validation

Execution SHALL be BLOCKED if approval metadata is incomplete.
```

---

## Risk Classification (replaces all doctrine categories)

| Risk Level | Definition | Approval Required |
|---|---|---|
| `read_only` | Observation, telemetry, reporting | None |
| `low` | Low-severity triggers (Severity < 3), logging | None (auto-proceed) |
| `medium` | High-severity student messages (Severity 3–5) | Human approval (1-hour SLA) |
| `high` | Additive schema changes via Alembic | Human approval (24-hour SLA) |
| `critical` | Any modification to production SQL Server objects | Human approval + 2 reviewers (48-hour SLA) |

---

## What Needs to Be Built (Sprint 1)

### 1. ApprovalRequests Table (Alembic migration 0010)

```sql
CREATE TABLE AI_ChatBot_ApprovalRequests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type     VARCHAR(50)  NOT NULL,
    scope_json      TEXT         NOT NULL,
    rollback_json   TEXT,
    status          VARCHAR(20)  NOT NULL DEFAULT 'pending',
    requested_by    VARCHAR(100),
    approved_by     VARCHAR(100),
    denial_reason   TEXT,
    requested_at    DATETIME     NOT NULL,
    decided_at      DATETIME,
    cbm_id          INTEGER,
    expires_at      DATETIME
);
```

### 2. GovernanceApprovalService

Methods: `request_approval()`, `approve()`, `deny()`, `require_approved()`, `list_pending()`

Full implementation spec: [audit/GOVERNANCE_MODEL.md](../../audit/GOVERNANCE_MODEL.md)

### 3. Severity Gate in DbTriggerProcessingService

```python
GOVERNANCE_THRESHOLD = 3  # severity >= 3 requires human approval

if rule.Severity is not None and rule.Severity >= GOVERNANCE_THRESHOLD:
    approval_id = GovernanceApprovalService().request_approval(...)
    return {"accepted": False, "pending_approval": True, "approval_id": approval_id}
# severity < 3: proceed immediately (existing code path)
```

### 4. API Routes

```
GET  /api/governance/pending        → list pending approvals
POST /api/governance/approve/{id}   → approve
POST /api/governance/deny/{id}      → deny
GET  /admin                         → HTML approval page (Jinja2, no React needed)
```

---

## Governance Invariants (6 lines — replaces 42 documents)

```
1. Every high-severity action creates an ApprovalRequest before execution
2. Humans approve or deny within the defined SLA
3. All decisions are written to ApprovalRequests (immutable after decision)
4. Production SQL Server core tables are never modified by the overlay system
5. Delivery outcomes are always persisted in DeliveryLog (success or failure)
6. No secrets, credentials, or PII are logged in plaintext
```

---

## Audit Trail (already sufficient for MVP)

For any trigger event, these 4 tables provide complete forensic reconstruction:

```
TriggeredUser.CBM_ID  → who, when, which rule, which student, outcome
EngagementEvent       → every action taken (indexed by trigger_id = CBM_ID)
DeliveryLog           → delivery success/failure with provider details
ChatBotAuditLog       → every message content (indexed by CBM_ID)
```

For governance decisions (after ApprovalRequests is built):
```
ApprovalRequest       → what was requested, who approved, when, why denied
```

---

## Full Specification

See [audit/GOVERNANCE_MODEL.md](../../audit/GOVERNANCE_MODEL.md) for:
- Complete `GovernanceApprovalService` Python class
- Full Alembic migration 0010
- Admin HTML template
- All 9 unit tests to write
