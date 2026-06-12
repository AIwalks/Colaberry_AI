# Directive: Governance Gate Contract

## 1. Purpose

`GovernanceGateService` solves one problem: **the delivery pipeline in
`MentorMessageService` sends student-facing messages without verifying that a
human reviewer has approved the AI interpretation that produced the
intervention**.

The Sentinel intelligence pipeline generates `AIInterpretation` records and
immediately enqueues them in `GovernanceReview` with `status="pending"`. The
purpose of that queue is to give a human reviewer the authority to confirm,
dispute, or defer the AI's risk assessment before any outbound action is taken.
Without a runtime gate, the queue is a post-hoc audit trail — not a meaningful
control.

`GovernanceGateService` inserts that control. Before `send_text()` is called,
it asks: *does an approved governance review exist for this student's current AI
interpretation?* If the answer is no, delivery is blocked and the reason is
recorded. If no Sentinel interpretation exists at all, delivery proceeds
unchanged — the gate must never disrupt the production engagement pipeline for
students the system has never evaluated.

This implements **FR-EXEC-001 — Approval-Gated Execution**:

> All executions SHALL require explicit approval. When approval metadata is
> incomplete, execution SHALL be blocked.

All gate logic is **deterministic**. Given the same database state,
`GovernanceGateService` must always return the same outcome. It does not call
any LLM, apply heuristic scoring, or vary its decision by time elapsed since
review creation. LLM-based or time-based approval is explicitly prohibited —
see Section 8.

---

## 2. `check_delivery_approved()` — Full Contract

### Signature

```python
def check_delivery_approved(
    self,
    db: Session,
    entity_id: str,
    entity_type: str = "student",
) -> dict:
```

### Parameters

| Parameter | Type | Notes |
|---|---|---|
| `db` | `Session` | SQLAlchemy session — read-only use; no commits or rollbacks issued |
| `entity_id` | `str` | Student identifier as a string. Must match `AIInterpretation.entity_id`. Callers are responsible for casting integer UserIDs to `str` before calling (e.g., `str(user_id)`). |
| `entity_type` | `str` | Defaults to `"student"`. Passed as-is to the `AIInterpretation` query. |

### Return shape

The method always returns a dict. It **never raises**.

| Key | Type | Always present? | Notes |
|---|---|---|---|
| `approved` | `bool` | Yes | `True` → delivery may proceed; `False` → delivery must be blocked |
| `reason` | `str` | Yes | One of the 7 outcome codes defined in Section 3 |
| `review_id` | `int` or `None` | Yes | PK of the `GovernanceReview` row when one exists; `None` otherwise |

### Session contract

`check_delivery_approved()` issues SELECT queries only. It does not call
`db.commit()`, `db.add()`, `db.rollback()`, or any write operation. The caller
must open a dedicated session for the gate check and must not share it with any
write path.

---

## 3. Decision Outcomes

There are exactly 7 outcomes. Each has a fixed `approved` value and `reason`
string. No other outcomes are valid.

### 3.1 `approved_review`

```
approved = True
reason   = "approved_review"
review_id = <int>
```

**Condition:** A latest active `AIInterpretation` exists for the student AND the
corresponding `GovernanceReview` has `status = "approved"`.

**Meaning:** A human reviewer has confirmed the AI's risk assessment is
actionable. Delivery may proceed.

---

### 3.2 `pending`

```
approved  = False
reason    = "pending"
review_id = <int>
```

**Condition:** A latest active `AIInterpretation` exists AND the corresponding
`GovernanceReview` has `status = "pending"`.

**Meaning:** The review queue has not yet been worked. A human has not reviewed
the AI output. Delivery must be blocked.

---

### 3.3 `rejected`

```
approved  = False
reason    = "rejected"
review_id = <int>
```

**Condition:** A latest active `AIInterpretation` exists AND the corresponding
`GovernanceReview` has `status = "rejected"`.

**Meaning:** A human reviewer has disputed the AI's interpretation. Acting on
a rejected interpretation would violate governance authority. Delivery must be
blocked.

---

### 3.4 `deferred`

```
approved  = False
reason    = "deferred"
review_id = <int>
```

**Condition:** A latest active `AIInterpretation` exists AND the corresponding
`GovernanceReview` has `status = "deferred"`.

**Meaning:** A reviewer has requested more information before a decision.
The interpretation is not yet actionable. Delivery must be blocked.

---

### 3.5 `no_governance_review`

```
approved  = False
reason    = "no_governance_review"
review_id = None
```

**Condition:** A latest active `AIInterpretation` exists BUT no
`GovernanceReview` row exists for it (i.e., `GovernanceReviewService
.create_pending_review()` failed silently when the interpretation was
generated).

**Meaning:** An interpretation was generated without a corresponding review
record — this indicates a pipeline fault. Treat as pending: delivery is blocked
until the governance record is repaired. The fault must be logged at ERROR
level.

**Why block rather than allow:** Allowing delivery with no review record would
make the approval gate bypassable through an orchestration failure. Missing
records must be treated conservatively.

---

### 3.6 `no_sentinel_data`

```
approved  = True
reason    = "no_sentinel_data"
review_id = None
```

**Condition:** No active `AIInterpretation` exists for this student (Sentinel
has never evaluated them, or all interpretations are invalidated).

**Meaning:** The Sentinel overlay has no opinion on this student. The legacy
trigger/delivery pipeline must work as it did before Sentinel existed. Delivery
proceeds without any governance gate. See Section 6 for the full compatibility
rule.

---

### 3.7 `gate_error`

```
approved  = True
reason    = "gate_error"
review_id = None
```

**Condition:** Any unhandled exception is raised during the gate check (e.g.,
DB connection failure, missing table, SQLAlchemy error).

**Meaning:** The gate infrastructure failed. The production delivery pipeline
must not be blocked by a monitoring layer outage. Delivery proceeds. The
exception must be logged at ERROR level with the `entity_id` and full exception
message. See Section 5 for the fail-open policy.

---

## 4. Query Behavior

### 4.1 Step 1 — AIInterpretation lookup

```sql
SELECT *
FROM   AI_ChatBot_AIInterpretations
WHERE  entity_id   = :entity_id
AND    entity_type = :entity_type
AND    is_active   = 1
ORDER  BY created_at DESC
LIMIT  1
```

**`is_active = True` is mandatory.** Invalidated interpretations (where
`is_active = False`) must not be used as the basis for a gate decision.
An invalidated interpretation means the system has moved on — the new active
interpretation (if any) must be queried instead.

| Result | Next step |
|---|---|
| Row found | Proceed to Step 2 with the interpretation's `id` |
| No row found | Return `no_sentinel_data` immediately — do not query `GovernanceReview` |

### 4.2 Step 2 — GovernanceReview lookup

```sql
SELECT *
FROM   AI_ChatBot_GovernanceReviews
WHERE  interpretation_id = :interpretation_id
ORDER  BY created_at DESC
LIMIT  1
```

There is no filter on `status` — the most recent review row for this
interpretation is loaded and its status inspected in application code.

| `GovernanceReview.status` | Outcome |
|---|---|
| `"approved"` | Return `approved_review` |
| `"pending"` | Return `pending` |
| `"rejected"` | Return `rejected` |
| `"deferred"` | Return `deferred` |
| No row found | Return `no_governance_review` |

**Why `ORDER BY created_at DESC LIMIT 1`:** A review can be re-deferred after
an initial decision (see `GovernanceReviewService.defer_review()` lifecycle).
The most recent row reflects the latest governance state.

### 4.3 entity_id type contract

`AIInterpretation.entity_id` is `String(100)`. `TriggeredUsers.UserID` is
`Integer`. The caller (e.g., `MentorMessageService.process_trigger()`) must
cast the integer to string before calling `check_delivery_approved()`:

```python
gate_result = GovernanceGateService().check_delivery_approved(
    db=gate_session,
    entity_id=str(user_id) if user_id is not None else "",
)
```

`GovernanceGateService` does not perform this cast internally — the caller
owns entity ID resolution. An empty string `""` is treated as a valid query
value; it will match no interpretation row and return `no_sentinel_data`.

---

## 5. Fail-Open Policy

**Any exception raised during `check_delivery_approved()` must be caught at
the outermost level. The gate must return `gate_error` (approved=True) and
must never propagate the exception to the caller.**

```python
try:
    # Step 1 + Step 2 queries
    ...
except Exception as exc:
    logger.error(
        "GovernanceGate: gate check failed for entity_id=%r — "
        "fail-open: delivery proceeding. Error: %s",
        entity_id, exc,
    )
    return {"approved": True, "reason": "gate_error", "review_id": None}
```

### Rationale

The Sentinel governance overlay is additive infrastructure built on top of a
production student engagement system. If the Sentinel database, its tables, or
the gate service itself encounters an error, the production engagement pipeline
must continue operating. A monitoring layer must not become a single point of
failure for outbound communications.

Corollaries:
- `gate_error` is a signal that requires investigation, not silent acceptance.
  The ERROR-level log is mandatory — it must not be suppressed.
- `gate_error` is not a mechanism for bypassing governance. It is a circuit
  breaker for infrastructure failures. If `gate_error` fires repeatedly for
  the same student, the root cause must be investigated and resolved.
- **This policy must not be changed to fail-closed without an architectural
  review.** Changing fail-open to fail-closed would block all student
  deliveries whenever the Sentinel DB is unavailable — a disproportionate
  impact on a safety-critical communication pipeline.

---

## 6. Legacy Compatibility Rule

The `no_sentinel_data` outcome exists to guarantee backward compatibility with
the existing trigger/delivery pipeline.

**Rule:** If `GovernanceGateService.check_delivery_approved()` finds no active
`AIInterpretation` for a student, it must return `approved=True`. The gate must
not block delivery for students the Sentinel intelligence layer has not yet
evaluated.

### Why this rule exists

The production engagement system (SQL Server triggers → TriggeredUsers →
MentorMessageService) predates the Sentinel overlay. Thousands of trigger
events may exist in the queue before Sentinel has evaluated any student. If the
gate blocked all delivery for un-evaluated students, every message would be
blocked until Sentinel had been run for every active student — an unacceptable
operational impact.

### What this rule permits

Any student without an active `AIInterpretation` is outside Sentinel's scope of
governance. Delivery for such students is permitted unconditionally and behaves
identically to the pre-Sentinel system.

### What this rule does NOT permit

Once Sentinel has generated an `AIInterpretation` for a student, the
`no_sentinel_data` path no longer applies — even if that interpretation is
later invalidated and no newer interpretation exists. In that case the query
returns no active interpretation, and `no_sentinel_data` is returned again.
This is correct: a student with only invalidated interpretations is treated as
unreviewed until Sentinel re-evaluates them.

### This rule must not be removed

Removing the `no_sentinel_data` fall-through without a migration plan that
ensures every active student has an approved interpretation would cause a
complete delivery blackout. Any change to this rule requires explicit
architectural approval and a migration plan.

---

## 7. Blocking Behavior

### When delivery is blocked

`process_trigger()` in `MentorMessageService` must return the following shape
when the gate returns `approved=False`, and must not call `send_text()`:

```python
return {
    "sent":      False,
    "reason":    "governance_review_required",
    "review_id": gate_result.get("review_id"),
    "cbm_id":    cbm_id,
}
```

The gate reason (e.g., `"pending"`, `"rejected"`) must be logged at INFO level
alongside the `entity_id`, `cbm_id`, and `review_id` so that the block is
auditable:

```
INFO GovernanceGate: delivery blocked for entity_id='101' cbm_id=1701
     reason=pending review_id=42
```

### When delivery is allowed

`send_text()` is called normally when:

| Gate outcome | `approved` | `send_text()` called? |
|---|---|---|
| `approved_review` | `True` | Yes |
| `no_sentinel_data` | `True` | Yes |
| `gate_error` | `True` | Yes |
| `pending` | `False` | **No** |
| `rejected` | `False` | **No** |
| `deferred` | `False` | **No** |
| `no_governance_review` | `False` | **No** |

### Gate placement in process_trigger()

The gate check must occur:
- **After** the atomic `UPDATE Completed=1 RETURNING` claim succeeds (the
  claim is durable; it must not be retried on a block).
- **Before** `OutboundDeliveryService.send_text()` is called.
- **In a separate session** (`SessionLocal() as gate_session`) — the gate
  session is read-only and must not be shared with the claim session or any
  write path.

The gate must **not** be called:
- On the `no_db` early-return path (MSSQL not configured).
- On the `not_found` path (no TriggeredUser row).
- On the `already_claimed` path (another worker claimed the row first).

### Commitment of Completed=1 before gate

The `UPDATE Completed=1` claim is committed before the gate runs. This is
intentional: if the gate blocks delivery, the trigger row remains in
`Completed=1` state. The message is not retried by the worker. This prevents
a blocked trigger from cycling endlessly through the queue. If a reviewer later
approves the interpretation, delivery must be manually re-triggered or the
trigger re-queued — automatic retry on approval is out of scope for Sprint 8.

---

## 8. Determinism Requirements

`GovernanceGateService` must be fully deterministic. Given the same database
state, it must always return the same outcome.

### Prohibited behaviors

**LLM-based approval is prohibited.** The gate must not call Claude or any
other AI service to decide whether delivery should proceed. Approval is a human
governance decision.

**Heuristic auto-approval is prohibited.** The gate must not implement logic
such as:
- "Auto-approve if confidence > 0.9"
- "Auto-approve low-risk interpretations"
- "Auto-approve if the reviewer hasn't acted within 48 hours"

Any such heuristic would undermine the purpose of the governance queue. The
only valid `approved_review` path is a human reviewer calling
`GovernanceReviewService.approve_review()`.

**Time-based logic is prohibited.** The gate must not inspect
`GovernanceReview.created_at` or `reviewed_at` to make a decision. Age of the
review is irrelevant to whether it has been approved.

### Why determinism matters

Non-deterministic gate decisions would make the delivery pipeline untestable
and ungovernable: the same trigger could be delivered or blocked depending on
AI output, system time, or confidence thresholds — all of which can change
independently of the actual human review decision.

---

## 9. Test Requirements

### Unit tests — `tests/unit/test_governance_gate_service.py`

All 7 outcomes must have explicit test coverage. No outcome may be left
untested. Tests must use mocked DB sessions — no MSSQL or SQLite required.

| Required test class | Coverage |
|---|---|
| `TestApprovedPath` | Active interpretation + approved review → `approved_review`; `review_id` present in return value |
| `TestBlockedPaths` | Active interpretation + pending review → `pending`; active + rejected → `rejected`; active + deferred → `deferred` |
| `TestNoGovernanceReview` | Active interpretation, no review row → `no_governance_review`; `approved=False`; `review_id=None` |
| `TestNoSentinelData` | No active interpretation → `no_sentinel_data`; `approved=True`; `review_id=None` |
| `TestNoSentinelDataEdgeCases` | Empty string entity_id → `no_sentinel_data`; invalidated interpretation only → `no_sentinel_data` |
| `TestFailOpen` | DB query raises exception → `gate_error`; `approved=True`; exception logged at ERROR; return value always has `approved` key |
| `TestReturnContract` | Return value is always a dict; `approved` key always present; `reason` always a str; `review_id` always int or None |

### Wiring tests — `tests/unit/test_mentor_message_trigger.py`

A `TestGovernanceGateWiring` class must be added after
`TestAdaptiveRecommendationWiring`.

| Required test | Verifies |
|---|---|
| Gate returns `approved_review` → `send_text()` is called | Happy path — gate does not block delivery |
| Gate returns `pending` → `send_text()` is NOT called | Delivery blocked on pending |
| Gate returns `pending` → `process_trigger()` returns `reason="governance_review_required"` | Correct return shape on block |
| Gate returns `no_sentinel_data` → `send_text()` IS called | Legacy fall-through preserved |
| Gate raises exception → `send_text()` IS called | Fail-open: gate error does not drop message |
| `already_claimed` path → gate is NOT called | Gate only called when delivery is intended |
| Gate called with `str(user_id)` when `user_id` is an integer | entity_id cast verified |

All wiring tests must patch `GovernanceGateService` at its import path in
`mentor_message_service`. Tests must use local SQLite — no MSSQL required.

### Mandatory pattern

Tests must follow the mocking patterns established in
`TestRecommendationTrackingTriggered` and `TestAdaptiveRecommendationWiring`.
Specifically:
- `MSSQL_CONFIGURED` patched to `True`
- `OutboundDeliveryService.send_text` patched to return fake results
- `GovernanceGateService` patched at the module-level import path

---

## 10. Definition of Done

A Sprint 8 implementation is not complete until all of the following are true:

- [ ] `services/governance_gate_service.py` exists and implements the 7-outcome
  contract from Section 3
- [ ] All unit tests in `TestGovernanceGateService` (Section 9) pass — 0 failures
- [ ] All wiring tests in `TestGovernanceGateWiring` (Section 9) pass — 0 failures
- [ ] `send_text()` is demonstrably not called when gate returns `approved=False`
  (verified by `assert mock_send.call_count == 0`)
- [ ] `send_text()` is demonstrably called when gate returns `gate_error`
  (verified by `assert mock_send.call_count == 1`)
- [ ] `no_sentinel_data` fall-through verified: student with no interpretation
  produces a normal delivery (not blocked)
- [ ] `gate_error` logs at ERROR level — verified in unit test
- [ ] No production service files (excluding `mentor_message_service.py`) are
  modified
- [ ] No existing tests are broken
- [ ] No new migrations are required (tables `AI_ChatBot_AIInterpretations` and
  `AI_ChatBot_GovernanceReviews` are already created by migrations 0010/0011)
- [ ] `PROGRESS.md` updated with Sprint 8 entry

### Threshold change process

No logic change may be made to `GovernanceGateService` without:
1. Updating this directive first
2. Updating the affected unit tests before changing the code
3. Getting explicit approval if the change affects the fail-open policy or the
   `no_sentinel_data` fall-through rule — both of which directly affect the
   production delivery pipeline
