# Directive: Governance Review API Contract

## 1. Purpose

`GovernanceReviewService` (Sprint 3) implements the human review lifecycle —
approve, reject, and defer — for AI-generated `AIInterpretation` records.
`GovernanceGateService` (Sprint 8) blocks outbound delivery until a review
with `status="approved"` exists for the student's active interpretation.

Without HTTP endpoints for the three decision actions, the governance loop is
broken: reviews are created automatically when interpretations are generated,
the gate blocks delivery, but there is no supported path for a human reviewer
to act on a review. Reviewers can see the queue via
`GET /sentinel/governance/reviews/pending` but cannot change its state through
any API.

This directive specifies the three POST endpoints that close the loop:

```
POST /sentinel/governance/reviews/{review_id}/approve
POST /sentinel/governance/reviews/{review_id}/reject
POST /sentinel/governance/reviews/{review_id}/defer
```

These endpoints are the **only** supported path for advancing a review's
status. Direct database writes are not a supported alternative.

### Relationship to other directives

| Directive | Role |
|---|---|
| `directives/governance_gate_contract.md` | Specifies how approved reviews allow delivery to proceed |
| This directive | Specifies how human reviewers produce those approved reviews |

---

## 2. System Context

The three endpoints delegate entirely to `GovernanceReviewService`. They
contain no business logic, no status transition rules, and no validation
beyond Pydantic schema parsing and the no-DB guard.

```
HTTP POST ──► route handler
                ├─ 503 if MSSQL_CONFIGURED=False
                ├─ open SessionLocal()
                ├─ call GovernanceReviewService.{approve,reject,defer}_review()
                │     ├─ ValueError("not found")  → HTTP 404
                │     └─ ValueError("is required") → HTTP 422
                └─ return GovernanceReviewRead (HTTP 200)
```

`GovernanceReviewService` is the single source of truth for status transition
rules, required-field enforcement, and audit logging. The route layer must not
re-implement any of those rules.

---

## 3. Endpoint Contracts

All three endpoints share these properties:

- **Router prefix:** `/sentinel` (inherited — do not add a second prefix)
- **Auth:** `require_api_key` dependency inherited from the router registration
  in `app/main.py`; no per-route auth annotation is needed or permitted
- **No-DB guard:** return HTTP 503 immediately if `MSSQL_CONFIGURED` is `False`
- **Session:** open one `SessionLocal()` per request; pass it to the service;
  the service owns committing
- **Success response:** `GovernanceReviewRead` from `api/schemas/governance_review.py`

---

### 3.1 Approve

```
POST /sentinel/governance/reviews/{review_id}/approve
```

**Intent:** A reviewer confirms the AI interpretation is accurate and
actionable. After approval, `GovernanceGateService` will allow delivery to
proceed for this student's trigger.

**Path parameter:**

| Parameter | Type | Description |
|---|---|---|
| `review_id` | int | PK of the `GovernanceReview` row to approve |

**Request body:** `GovernanceReviewApprove`

| Field | Type | Required | Constraint | Description |
|---|---|---|---|---|
| `reviewed_by` | str | yes | min_length=1 | Identity of the reviewer (name, email, or system ID) |
| `review_notes` | str or null | no | none | Optional free-text annotation |

**Success response (200):** `GovernanceReviewRead` with `status="approved"`,
`reviewed_by` and `reviewed_at` set.

**Error responses:**

| Code | Condition |
|---|---|
| 400 | Not used |
| 401/403 | Missing or invalid `X-Api-Key` header |
| 404 | `review_id` does not exist in `GovernanceReview` |
| 422 | `reviewed_by` is empty (Pydantic) |
| 503 | `MSSQL_CONFIGURED=False` |

---

### 3.2 Reject

```
POST /sentinel/governance/reviews/{review_id}/reject
```

**Intent:** A reviewer disputes the AI interpretation. Delivery remains
blocked. A rejection without a stated reason is not an auditable governance
decision — `review_notes` is mandatory.

**Path parameter:**

| Parameter | Type | Description |
|---|---|---|
| `review_id` | int | PK of the `GovernanceReview` row to reject |

**Request body:** `GovernanceReviewReject`

| Field | Type | Required | Constraint | Description |
|---|---|---|---|---|
| `reviewed_by` | str | yes | min_length=1 | Identity of the reviewer |
| `review_notes` | str | yes | min_length=1 | Required explanation of why the interpretation was rejected |

**Success response (200):** `GovernanceReviewRead` with `status="rejected"`,
`reviewed_by`, `reviewed_at`, and `review_notes` set.

**Error responses:**

| Code | Condition |
|---|---|
| 401/403 | Missing or invalid `X-Api-Key` header |
| 404 | `review_id` does not exist |
| 422 | `reviewed_by` is empty (Pydantic); `review_notes` is empty or absent (Pydantic); `review_notes` is whitespace-only (service ValueError) |
| 503 | `MSSQL_CONFIGURED=False` |

---

### 3.3 Defer

```
POST /sentinel/governance/reviews/{review_id}/defer
```

**Intent:** A reviewer needs more information before making a final decision.
Delivery remains blocked. A deferral without a stated reason is not an
auditable governance decision — `governance_reason` is mandatory.

**Path parameter:**

| Parameter | Type | Description |
|---|---|---|
| `review_id` | int | PK of the `GovernanceReview` row to defer |

**Request body:** `GovernanceReviewDefer`

| Field | Type | Required | Constraint | Description |
|---|---|---|---|---|
| `reviewed_by` | str | yes | min_length=1 | Identity of the reviewer |
| `governance_reason` | str | yes | min_length=1 | Required explanation of what additional information is needed |

**Success response (200):** `GovernanceReviewRead` with `status="deferred"`,
`reviewed_by`, `reviewed_at`, and `governance_reason` updated.

**Error responses:**

| Code | Condition |
|---|---|
| 401/403 | Missing or invalid `X-Api-Key` header |
| 404 | `review_id` does not exist |
| 422 | `reviewed_by` is empty (Pydantic); `governance_reason` is empty or absent (Pydantic); `governance_reason` is whitespace-only (service ValueError) |
| 503 | `MSSQL_CONFIGURED=False` |

---

## 4. Request Body Schemas

These schemas exist in `api/schemas/governance_review.py` and must not be
modified to implement these endpoints.

### `GovernanceReviewApprove`

```python
class GovernanceReviewApprove(BaseModel):
    reviewed_by:  str           = Field(min_length=1)
    review_notes: Optional[str] = None
```

### `GovernanceReviewReject`

```python
class GovernanceReviewReject(BaseModel):
    reviewed_by:  str = Field(min_length=1)
    review_notes: str = Field(min_length=1)
```

Note: `min_length=1` prevents empty string but not whitespace-only.
`GovernanceReviewService.reject_review()` enforces the whitespace check and
raises `ValueError` if `review_notes.strip()` is falsy.

### `GovernanceReviewDefer`

```python
class GovernanceReviewDefer(BaseModel):
    reviewed_by:       str = Field(min_length=1)
    governance_reason: str = Field(min_length=1)
```

Note: same whitespace rule applies — service enforces `governance_reason.strip()`.

---

## 5. Success Response Schema

All three endpoints return `GovernanceReviewRead` on success (HTTP 200).

```python
class GovernanceReviewRead(BaseModel):
    id:                  int
    created_at:          datetime
    updated_at:          datetime
    interpretation_id:   int
    entity_id:           str
    entity_type:         str
    status:              GovernanceReviewStatus   # "approved" | "rejected" | "deferred"
    reviewed_by:         Optional[str]
    reviewed_at:         Optional[datetime]
    review_notes:        Optional[str]
    governance_reason:   str
    risk_level:          str
    confidence:          float
    audit_snapshot_json: Optional[dict]
    is_active:           bool

    model_config = {"from_attributes": True}
```

The response is produced via `GovernanceReviewRead.model_validate(review)`
where `review` is the `GovernanceReview` ORM object returned by the service.

---

## 6. Error Behavior

### 6.1 ValueError dispatch

`GovernanceReviewService` raises `ValueError` in two distinct situations.
The route handler must distinguish them:

| `ValueError` message contains | HTTP status | When raised |
|---|---|---|
| `"not found"` | 404 | `review_id` does not exist (`_load_or_raise`) |
| `"is required"` | 422 | Required field is whitespace-only |

Recommended handler pattern:

```python
try:
    review = svc.approve_review(db, review_id=review_id, ...)
except ValueError as exc:
    msg = str(exc)
    if "not found" in msg:
        raise HTTPException(status_code=404, detail=msg)
    raise HTTPException(status_code=422, detail=msg)
```

### 6.2 Pydantic validation (422)

FastAPI returns HTTP 422 automatically when the request body fails Pydantic
validation. The route handler does not need to handle this case explicitly.

Cases that Pydantic catches before the handler runs:
- `reviewed_by` is `""` or absent
- `review_notes` is `""` or absent for reject
- `governance_reason` is `""` or absent for defer

Cases that reach the service (Pydantic passes, service raises):
- `review_notes` is `"   "` (whitespace-only) on reject
- `governance_reason` is `"   "` (whitespace-only) on defer

### 6.3 Auth (401/403)

The `require_api_key` dependency is applied at the router level in
`app/main.py`:

```python
app.include_router(sentinel_router, dependencies=[Depends(require_api_key)])
```

All three action endpoints inherit this dependency. No per-route auth
annotation is needed. Missing or invalid `X-Api-Key` header returns 401/403
before the handler body executes.

---

## 7. No-DB Guard

When `MSSQL_CONFIGURED` is `False`, the SQL Server database is unavailable.
The action endpoints must return HTTP 503 and must not call any service method.

```python
from config.database import MSSQL_CONFIGURED, SessionLocal

if not MSSQL_CONFIGURED:
    raise HTTPException(status_code=503, detail="no_db")
```

This mirrors the behavior of `MentorMessageService.process_trigger()` which
returns `{"sent": False, "reason": "no_db"}` when the database is not
configured.

**Why 503 and not 404:** The resource may exist once the database becomes
available. The client should retry when the database is configured. HTTP 503
(Service Unavailable) is semantically correct; 404 would imply the resource
does not exist.

The mock-data fallback used by the GET governance endpoints is not appropriate
for write actions. Write endpoints must always operate on the real database.

---

## 8. Idempotency and Repeated Actions

`GovernanceReviewService` does not guard against re-applying a decision to
an already-decided review. The service's `_load_or_raise()` loads the review
by PK regardless of its current status and applies the new status.

Consequences:

| Scenario | Outcome |
|---|---|
| Approve an already-approved review | Succeeds; `reviewed_at` is updated to now |
| Reject an already-approved review | Succeeds; status changes to "rejected" |
| Defer then re-defer | Succeeds; `governance_reason` and `reviewed_at` are overwritten |
| Approve after rejection | Succeeds; `GovernanceGateService` will then allow delivery |

**This behavior is intentional.** The service docstring documents the
`any → deferred` edge case explicitly. Governance decisions are not immutable
in the database; the most recent decision governs. The full decision history
is preserved in application logs (`logger.info` in the service).

**The route layer must not add guards against re-application.** That would
be business logic in the wrong layer. If the system's governance policy
changes to require immutable first decisions, that change belongs in
`GovernanceReviewService`, not in the route.

---

## 9. Test Requirements

Tests live in `tests/unit/test_governance_review_route.py`.

All tests must use `FastAPI.TestClient` with `GovernanceReviewService`
patched at its import path inside the route module. No real database is
required.

### `TestApproveEndpoint`

| Test | Verifies |
|---|---|
| Valid approve body → 200, response contains `status="approved"` | Happy path; service called with correct kwargs |
| `review_id` not in DB (service raises `ValueError("not found")`) → 404 | Not-found path |
| `reviewed_by` empty string → 422 (Pydantic) | Input validation |
| `MSSQL_CONFIGURED=False` → 503, service not called | No-DB guard |
| Missing `X-Api-Key` → 401/403 | Auth guard |

### `TestRejectEndpoint`

| Test | Verifies |
|---|---|
| Valid reject body with `review_notes` → 200, `status="rejected"` | Happy path |
| `review_id` not found → 404 | Not-found path |
| `review_notes` absent or `""` → 422 (Pydantic) | Required field validation |
| `review_notes` whitespace-only (service ValueError) → 422 | Service-layer whitespace check |
| `MSSQL_CONFIGURED=False` → 503, service not called | No-DB guard |
| Missing `X-Api-Key` → 401/403 | Auth guard |

### `TestDeferEndpoint`

| Test | Verifies |
|---|---|
| Valid defer body with `governance_reason` → 200, `status="deferred"` | Happy path |
| `review_id` not found → 404 | Not-found path |
| `governance_reason` absent or `""` → 422 (Pydantic) | Required field validation |
| `governance_reason` whitespace-only (service ValueError) → 422 | Service-layer whitespace check |
| `MSSQL_CONFIGURED=False` → 503, service not called | No-DB guard |
| Missing `X-Api-Key` → 401/403 | Auth guard |

### `TestAuthGuard`

| Test | Verifies |
|---|---|
| Approve endpoint — no API key | Returns 401/403 |
| Reject endpoint — no API key | Returns 401/403 |
| Defer endpoint — no API key | Returns 401/403 |

### Test patterns

- Patch `GovernanceReviewService` at its import path within the route module
  (e.g., `"api.routes.sentinel.GovernanceReviewService"` or equivalent for
  new file)
- For no-DB tests: patch `MSSQL_CONFIGURED` to `False` at the route module
  import path
- For auth tests: omit the `X-Api-Key` header from `TestClient`
- No SQLite or MSSQL required — all DB interaction is mocked
- Return value from mock service should be a `SimpleNamespace` or `MagicMock`
  with the fields needed by `GovernanceReviewRead.model_validate()`

---

## 10. Code Map

| Responsibility | File |
|---|---|
| Action endpoint implementation | `api/routes/sentinel.py` (add three POST routes) |
| Request body schemas | `api/schemas/governance_review.py` (existing — do not modify) |
| Response schema | `api/schemas/governance_review.py` → `GovernanceReviewRead` |
| Business logic / status transitions | `services/governance_review_service.py` (do not modify) |
| Gate that reads the results | `services/governance_gate_service.py` (do not modify) |
| Auth dependency | `config/auth.py` → `require_api_key` (inherited from router) |
| DB availability flag | `config/database.py` → `MSSQL_CONFIGURED` |
| Unit tests | `tests/unit/test_governance_review_route.py` (new) |

---

## 11. Definition of Done

- [ ] `POST /sentinel/governance/reviews/{review_id}/approve` exists and
  returns 200 / `GovernanceReviewRead` when `GovernanceReviewService.approve_review()`
  succeeds
- [ ] `POST /sentinel/governance/reviews/{review_id}/reject` exists and
  returns 200 / `GovernanceReviewRead` when `GovernanceReviewService.reject_review()`
  succeeds
- [ ] `POST /sentinel/governance/reviews/{review_id}/defer` exists and
  returns 200 / `GovernanceReviewRead` when `GovernanceReviewService.defer_review()`
  succeeds
- [ ] All three endpoints return 404 when the service raises `ValueError`
  containing "not found"
- [ ] All three endpoints return 422 when the service raises `ValueError`
  containing "is required" (whitespace-only input that bypassed Pydantic)
- [ ] All three endpoints return 503 when `MSSQL_CONFIGURED=False`; service
  is never called
- [ ] All three endpoints return 401/403 when `X-Api-Key` is absent or
  invalid; service is never called
- [ ] No business logic added to route handlers — all decisions delegated
  to `GovernanceReviewService`
- [ ] `GovernanceReviewService` is not modified
- [ ] `GovernanceGateService` is not modified
- [ ] `api/schemas/governance_review.py` is not modified
- [ ] `tests/unit/test_governance_review_route.py` exists with all test
  classes from Section 9 passing
- [ ] Full unit test suite passes with 0 failures
- [ ] `PROGRESS.md` updated with Sprint 9 entry
