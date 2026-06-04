# EVENT MODEL — MAXIMUM RIGOR EDITION
**Colaberry Sentinel OS | Date: 2026-05-07**

---

## PART A — WHAT "REPLAY-SAFE" MEANS AND DOES NOT MEAN

### What Replay Actually Means (Technical Definition)

In event sourcing architecture, "replay-safe" means:

1. **State is derived from events, not stored directly.** You don't store `Completed=1`; you store `TriggerClaimedEvent` and derive completion from it.

2. **Events are immutable and append-only.** No UPDATE, no DELETE on the event store.

3. **Handlers are deterministic.** Given event E, the handler always produces the same state S. No side effects that vary by time (e.g., Twilio calls during replay would send real messages — which is catastrophic).

4. **Replay executes the handler sequence from time T₀ (or snapshot) to Tₙ.** The system must have a replay executor: `for event in event_store: handler(event)`.

5. **Idempotency keys prevent duplicate side effects.** If a Twilio message was sent and you replay, the idempotency key tells Twilio "already sent, don't send again."

6. **Event schemas are versioned.** An event written 18 months ago with schema v1 must still be processable when v3 is current.

### What This System Has (Audit Trails, Not Replay)

The system has three append-only tables:
- `AI_ChatBot_AuditLog` — every message sent and received
- `AI_ChatBot_EngagementEvents` — every action taken
- `AI_ChatBot_DeliveryLog` — every delivery attempt

These provide **forensic reconstruction**: given a CBM_ID, you can query all three tables and understand exactly what happened, in what order, with what outcome.

This is **valuable and sufficient for MVP**.

### The Gap Between Doctrine and Reality

The doctrine says: "replay-safe operations." This implies a replay executor.

The reality: There is no replay executor. There are no versioned event schemas. The atomic claim operation (`UPDATE WHERE Completed=0`) cannot be replayed (it would silently fail on second run because Completed=1). The Twilio send cannot be replayed idempotently (it would send a duplicate SMS). The `EngagementEvent.created_at` is set at insert time, not preserved from event creation — so re-running handlers would produce wrong timestamps.

**The system is audit-safe, not replay-safe. This is fine for MVP. The terminology is wrong.**

---

## PART B — WHAT "REPLAY" SHOULD MEAN FOR THIS SYSTEM

### Tier 1: Forensic Reconstruction (IMPLEMENTED)

> "Given any CBM_ID, a human can reconstruct the complete lifecycle of that trigger event."

```python
# This is achievable today with existing tables:

def reconstruct_trigger_lifecycle(cbm_id: int) -> dict:
    triggered_user = session.get(TriggeredUser, cbm_id)
    audit_logs = session.execute(
        select(ChatBotAuditLog).where(ChatBotAuditLog.CBM_ID == cbm_id)
    ).scalars().all()
    engagement_events = session.execute(
        select(EngagementEvent).where(EngagementEvent.trigger_id == cbm_id)
    ).scalars().all()
    delivery_logs = session.execute(
        select(DeliveryLog).where(DeliveryLog.cbm_id == cbm_id)
    ).scalars().all()
    student_responses = session.execute(
        select(StudentResponse).where(StudentResponse.cbm_id == cbm_id)
    ).scalars().all()
    return {
        "trigger": triggered_user,
        "audit": audit_logs,
        "events": engagement_events,
        "deliveries": delivery_logs,
        "responses": student_responses,
    }
```

This is 20 lines of code. It already works with the existing schema. Build this as a `GET /api/audit/trigger/{cbm_id}` endpoint.

### Tier 2: Governance Decision Replay (TO BUILD)

> "Given any approval decision, reconstruct who approved it, when, and what was approved."

```
When ApprovalRequests table is built:
  SELECT * FROM ApprovalRequests WHERE cbm_id = ?
  → returns: action_type, scope_json, status, approved_by, decided_at
```

This is the governance audit trail. Build it as part of GovernanceApprovalService.

### Tier 3: Event Sourcing (DO NOT BUILD FOR MVP)

> "Reconstruct system state from scratch by re-executing the event log."

Requirements:
- Single event store (all state-changing events in one stream)
- Versioned event schemas
- Deterministic handlers with idempotency keys
- Snapshot mechanism
- Replay executor

**Do not build this.** It is 8–12 weeks of work. The system does not need it. The audit trail provides 95% of the value at 5% of the cost.

---

## PART C — DOCTRINE REPLAY CLAIMS: TESTABLE VS. IMPOSSIBLE

| Doctrine Claim | Testable? | Verdict |
|---|---|---|
| "All actions log to append-only tables" | YES — verify no UPDATE/DELETE in service code | TESTABLE — already true |
| "Audit logs are timestamped" | YES — query created_at on EngagementEvent | TESTABLE — already true |
| "Actor attribution on all actions" | PARTIAL — agent_name on EngagementEvent, but no human actor for most | PARTIAL |
| "Trigger lifecycle is reconstructable from CBM_ID" | YES — 4 queries across existing tables | TESTABLE — achievable now |
| "Approval decisions are auditable" | NO — ApprovalRequests table doesn't exist yet | BUILD FIRST |
| "Governance replay" | NO — governance engine doesn't exist | NOT TESTABLE |
| "Recommendation replay" | NO — InsightGenerator has no replay anchor | NOT TESTABLE |
| "Deployment replay" | NO — no deployment tracking table | NOT TESTABLE |
| "Institutional sequencing" | NO — undefined concept | NOT TESTABLE |
| "Replay-safe species governance" | NO — physically impossible to define | DELETE |
| "Infinite replay reconstructability" | NO — storage is finite | DELETE |
| "Eternal constitutional replay" | NO — eternal is not a system property | DELETE |

---

## PART D — ACTUAL EVENT TAXONOMY (WHAT EXISTS)

### EngagementEvent.event_type Values (from code)

```python
# In services/trigger_processing_service.py:
"trigger"                  # trigger evaluation completed

# In services/mentor_message_service.py:
"incoming_message"         # student sent a message
"trigger_dispatched"       # trigger claimed and dispatch initiated

# In code comments/tests (implied):
"nudge_sent"
"message_delivered"
"message_failed"
"response_matched"
"fingerprint_updated"
"insight_generated"
```

**PROBLEM:** These are string literals scattered across files. There is no:
- Enum or constants module defining valid values
- Validation on insert
- Documentation of the complete taxonomy

**FIX:** Create `services/event_types.py`:

```python
class EngagementEventType:
    TRIGGER_EVALUATED = "trigger_evaluated"
    TRIGGER_DISPATCHED = "trigger_dispatched"
    INCOMING_MESSAGE = "incoming_message"
    MESSAGE_DELIVERED = "message_delivered"
    MESSAGE_FAILED = "message_failed"
    RESPONSE_MATCHED = "response_matched"
    INSIGHT_GENERATED = "insight_generated"
    FINGERPRINT_UPDATED = "fingerprint_updated"
    # Governance (when built):
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
```

### ChatBotAuditLog.entry_type Values (from code)

```python
"incoming_message"    # mentor_message_service.py:48
"outbound_trigger"    # mentor_message_service.py:133
```

These are the only two types confirmed in code. No enum.

---

## PART E — MINIMUM REPLAY IMPLEMENTATION FOR MVP

MVP replay capability is 4 API endpoints + no new tables:

```
GET /api/audit/trigger/{cbm_id}
  Returns: TriggeredUser + all EngagementEvents + all DeliveryLogs + all ChatBotAuditLogs + StudentResponses
  WHERE: trigger_id/cbm_id = cbm_id
  Purpose: Complete forensic reconstruction of one trigger lifecycle

GET /api/audit/student/{user_id}?since=ISO8601&until=ISO8601
  Returns: all TriggeredUsers + all EngagementEvents for a student
  Purpose: Student lifecycle reconstruction

GET /api/audit/delivery-failures?since=ISO8601
  Returns: all DeliveryLog rows WHERE success=False
  Purpose: Operational health check (which messages failed to send)

GET /api/audit/approval/{approval_id}
  Returns: ApprovalRequest row with full decision history
  Purpose: Governance audit trail (requires ApprovalRequests table)
```

This is all the "replay" the system needs for MVP. Build it in 1 week.

---

## PART F — ENTERPRISE REPLAY IMPLEMENTATION (LATER)

When (if) the system needs true event sourcing:

**Trigger:** You discover a bug in the trigger evaluation logic and need to re-evaluate historical triggers with the corrected logic. Audit logs alone cannot do this — you need to re-execute the handler.

**Implementation path:**
1. Create `AI_ChatBot_EventStore` (id, aggregate_id, aggregate_type, event_type, payload_json, schema_version, created_at)
2. Define `TriggerEventAggregate` with handlers for each event type
3. Write events for every state change (instead of direct DB updates)
4. Build `EventReplayService` that reconstructs aggregate state from events
5. Add idempotency keys to all external calls (Twilio SID as idempotency token)
6. Migrate existing tables to derive from event store

**Estimated effort:** 8–12 weeks. Only justified if you have a concrete operational need for re-processing historical events with corrected logic.

---

## PART G — WHAT TO DO WITH THE DOCTRINE'S REPLAY LANGUAGE

**Every instance of "replay-safe"** in constitutional documents should be replaced with one of:

1. `"forensically auditable"` — if the claim is about audit trails (which it almost always is)
2. `"idempotent"` — if the claim is about safe retry behavior
3. `"append-only persisted"` — if the claim is about immutable logging
4. `"event-sourced"` — ONLY if actual event sourcing is built

The word "replay-safe" should not appear in any document until a replay executor exists in code.
