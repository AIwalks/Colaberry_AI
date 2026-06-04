# GOVERNANCE MODEL — MAXIMUM RIGOR EDITION
**Colaberry Sentinel OS | Date: 2026-05-07**

---

## PART A — WHAT GOVERNANCE ACTUALLY REQUIRES (FROM THE SPEC)

From `spec/01_requirements.md`, FR-GOV-001 and FR-EXEC-001:

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

**Current compliance: 0%.** The system executes immediately, autonomously, with no approval gate.

---

## PART B — WHAT GOVERNANCE IS NOT

The 42 constitutional doctrine files define governance as if it is a civilization-preserving constitutional framework requiring "Eternal Governance Coordinators", "Executive Closure Runtimes", "Constitutional Humanity Preservation", and "Species Continuity Sustainability."

**Governance for a student outreach chatbot is:**

1. A table that records pending action requests
2. A UI that shows pending requests to a human
3. A button that approves or denies
4. A check in the execution path that blocks if not approved
5. An audit trail that records who approved what

That is all. Build it in 2–3 weeks.

---

## PART C — GOVERNANCE IMPLEMENTATION SPECIFICATION

### Step 1: Migration 0010 — ApprovalRequests Table

```python
# alembic/versions/0010_add_approval_requests_table.py

def upgrade() -> None:
    op.create_table(
        "AI_ChatBot_ApprovalRequests",
        sa.Column("id",             sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("action_type",    sa.String(50),   nullable=False),
        sa.Column("scope_json",     sa.Text(),       nullable=False),
        sa.Column("rollback_json",  sa.Text(),       nullable=True),
        sa.Column("status",         sa.String(20),   nullable=False, server_default="pending"),
        sa.Column("requested_by",   sa.String(100),  nullable=True),
        sa.Column("approved_by",    sa.String(100),  nullable=True),
        sa.Column("denial_reason",  sa.Text(),       nullable=True),
        sa.Column("requested_at",   sa.DateTime(),   nullable=False),
        sa.Column("decided_at",     sa.DateTime(),   nullable=True),
        sa.Column("cbm_id",         sa.Integer(),    nullable=True),
        sa.Column("expires_at",     sa.DateTime(),   nullable=True),
    )
    op.create_index("ix_approval_requests_status", "AI_ChatBot_ApprovalRequests", ["status"])
    op.create_index("ix_approval_requests_cbm_id", "AI_ChatBot_ApprovalRequests", ["cbm_id"])
```

### Step 2: GovernanceApprovalService

```python
# services/governance_approval_service.py

from datetime import datetime
from sqlalchemy import select
from config.database import SessionLocal
from services.models import ApprovalRequest  # (new model)

class GovernanceError(Exception):
    """Raised when governance check fails."""

class PendingApprovalError(GovernanceError):
    """Raised when execution requires approval that is pending."""
    def __init__(self, approval_id: int):
        self.approval_id = approval_id
        super().__init__(f"Execution requires approval. approval_id={approval_id}")

class GovernanceApprovalService:

    def request_approval(
        self,
        action_type: str,
        scope: dict,
        rollback: dict | None = None,
        requested_by: str = "system",
        cbm_id: int | None = None,
    ) -> int:
        """Create a pending approval request. Returns approval ID."""
        import json
        with SessionLocal() as session:
            req = ApprovalRequest(
                action_type  = action_type,
                scope_json   = json.dumps(scope),
                rollback_json = json.dumps(rollback) if rollback else None,
                status       = "pending",
                requested_by = requested_by,
                requested_at = datetime.utcnow(),
                cbm_id       = cbm_id,
            )
            session.add(req)
            session.commit()
            session.refresh(req)
            return req.id

    def approve(self, approval_id: int, approver: str) -> None:
        with SessionLocal() as session:
            req = session.get(ApprovalRequest, approval_id)
            if req is None:
                raise GovernanceError(f"ApprovalRequest {approval_id} not found")
            req.status = "approved"
            req.approved_by = approver
            req.decided_at = datetime.utcnow()
            session.commit()

    def deny(self, approval_id: int, approver: str, reason: str) -> None:
        with SessionLocal() as session:
            req = session.get(ApprovalRequest, approval_id)
            if req is None:
                raise GovernanceError(f"ApprovalRequest {approval_id} not found")
            req.status = "denied"
            req.approved_by = approver
            req.denial_reason = reason
            req.decided_at = datetime.utcnow()
            session.commit()

    def require_approved(self, approval_id: int) -> None:
        """Block execution if not approved. Call before every governed action."""
        with SessionLocal() as session:
            req = session.get(ApprovalRequest, approval_id)
            if req is None:
                raise GovernanceError(f"ApprovalRequest {approval_id} not found")
            if req.status != "approved":
                raise GovernanceError(
                    f"Execution blocked: approval_id={approval_id} status={req.status}"
                )

    def list_pending(self) -> list[dict]:
        with SessionLocal() as session:
            rows = session.execute(
                select(ApprovalRequest).where(ApprovalRequest.status == "pending")
                .order_by(ApprovalRequest.requested_at)
            ).scalars().all()
            return [
                {
                    "id": r.id, "action_type": r.action_type,
                    "scope": r.scope_json, "requested_by": r.requested_by,
                    "requested_at": r.requested_at.isoformat(),
                    "cbm_id": r.cbm_id,
                }
                for r in rows
            ]
```

### Step 3: Gate in DbTriggerProcessingService

```python
# In DbTriggerProcessingService.process(), after rule lookup:

GOVERNANCE_THRESHOLD = 3  # severity >= 3 requires human approval

if rule.Severity is not None and rule.Severity >= GOVERNANCE_THRESHOLD:
    approval_id = GovernanceApprovalService().request_approval(
        action_type="trigger_dispatch_high_severity",
        scope={
            "trigger_type": trigger_type,
            "student_id": student_id,
            "kpi": rule.KPI,
            "severity": rule.Severity,
        },
        rollback={"action": "mark_triggered_user_completed", "note": "No message sent yet"},
        requested_by="DbTriggerProcessingService",
        cbm_id=None,  # CBM_ID not yet created; created after approval
    )
    return {
        "event_id": event_id,
        "accepted": False,
        "pending_approval": True,
        "approval_id": approval_id,
        "actions_planned": [],
        "notes": f"High-severity trigger requires human approval. approval_id={approval_id}",
    }
# If severity < threshold: proceed immediately (existing code path)
```

### Step 4: Admin API Routes

```python
# api/routes/governance.py

router = APIRouter(prefix="/api/governance")

@router.get("/pending")
def list_pending_approvals():
    """Return all pending approval requests."""
    return GovernanceApprovalService().list_pending()

@router.post("/approve/{approval_id}")
def approve_request(approval_id: int, body: ApproveRequest):
    """Approve a pending request."""
    GovernanceApprovalService().approve(approval_id, body.approver)
    return {"approved": True, "approval_id": approval_id}

@router.post("/deny/{approval_id}")
def deny_request(approval_id: int, body: DenyRequest):
    """Deny a pending request."""
    GovernanceApprovalService().deny(approval_id, body.approver, body.reason)
    return {"denied": True, "approval_id": approval_id}
```

### Step 5: Minimal Admin UI

A single HTML page served by FastAPI:

```html
<!-- templates/admin.html -->
<table>
  <tr><th>ID</th><th>Action</th><th>Student</th><th>Severity</th><th>Requested</th><th>Actions</th></tr>
  {% for req in pending %}
  <tr>
    <td>{{ req.id }}</td>
    <td>{{ req.action_type }}</td>
    <td>{{ req.scope.student_id }}</td>
    <td>{{ req.scope.severity }}</td>
    <td>{{ req.requested_at }}</td>
    <td>
      <button onclick="approve({{ req.id }})">Approve</button>
      <button onclick="deny({{ req.id }})">Deny</button>
    </td>
  </tr>
  {% endfor %}
</table>
```

Total implementation: 2–3 weeks including tests.

---

## PART D — GOVERNANCE RISK LEVELS (REPLACES ALL DOCTRINE CATEGORIES)

Replace "OPERATIONAL_CONSTITUTIONAL_CLOSURE / GOVERNANCE_CONSTITUTIONAL_CLOSURE / ETHICAL_CONSTITUTIONAL_CLOSURE / SECURITY_CONSTITUTIONAL_CLOSURE / AUDIT_CONSTITUTIONAL_CLOSURE / CONSTITUTIONAL_CONSTITUTIONAL_CLOSURE" with:

| Risk Level | Definition | Approval Required | Response Time |
|---|---|---|---|
| `read_only` | Observation, telemetry, reporting | None | Immediate |
| `low` | Low-severity triggers (Severity < 3), logging, KPI scoring | None (auto) | Immediate |
| `medium` | High-severity student messages (Severity 3–5) | Human approval | 1 hour SLA |
| `high` | Additive schema changes via Alembic | Human approval | 24 hour SLA |
| `critical` | Any modification to production SQL Server objects | Human approval + 2 reviewers | 48 hour SLA |

This is the complete governance model. Everything in the 42 doctrine files maps to one row in this table.

---

## PART E — GOVERNANCE INVARIANTS (SIMPLIFIED TO 6 LINES)

```
1. Every high-severity action creates an ApprovalRequest before execution
2. Humans approve or deny within the defined SLA
3. All decisions are written to ApprovalRequests (immutable after decision)
4. Production SQL Server core tables are never modified by the overlay system
5. Delivery outcomes are always persisted in DeliveryLog (success or failure)
6. No secrets, credentials, or PII are logged in plaintext
```

These 6 lines replace 42 documents. They are testable. Write tests for each.

---

## PART F — AUDIT MODEL (ALREADY SUFFICIENT FOR MVP)

The existing tables provide complete governance auditability:

```
For any trigger event:
  TriggeredUser.CBM_ID → who, when, which rule, which student, outcome
  EngagementEvent → every action taken
  DeliveryLog → delivery success/failure with provider details
  ChatBotAuditLog → every message content

For any governance decision (after ApprovalRequests is built):
  ApprovalRequest → what was requested, who approved, when, why denied

For any system health check:
  SELECT count(*) FROM AI_ChatBot_DeliveryLog WHERE success=False AND created_on > ?
  SELECT count(*) FROM AI_ChatBot_ApprovalRequests WHERE status='pending' AND expires_at < NOW()
```

No additional audit infrastructure is needed. Do not build "immutable audit chains with cryptographic tamper detection" for a student chatbot at this scale.

---

## PART G — WHAT THE CONSTITUTIONAL DOCTRINE GETS RIGHT

To be fair: the philosophical direction in the constitutional documents is correct. The underlying values are sound:

- Humans should have final authority ✓
- All actions should be auditable ✓
- AI recommendations should be explainable ✓
- Production systems should not be mutated silently ✓
- Environments should be isolated ✓

The problem is not the values — it is the scale of the language used to express them and the complete absence of implementation. These correct principles are already captured in CLAUDE.md, spec/01_requirements.md, and the architecture docs. They do not need 42 additional files to restate them with synonym substitution.
