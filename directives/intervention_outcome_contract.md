# Directive: Intervention Outcome Contract

## 1. Purpose

`InterventionOutcomeService` tracks whether a student's condition improved after an
advisor intervention was delivered. It answers one question per trigger:

> Did this student's engagement improve after we reached out?

It does this by:
1. **Enrolling** one `AI_ChatBot_InterventionOutcomes` row per trigger at delivery
   time, capturing a before-state snapshot of the student's activity level.
2. **Evaluating** enrolled rows after a fixed window has closed, comparing the
   before-state to the current after-state to classify each record as
   `improved`, `not_improved`, or `inconclusive`.

The outcome labels are used by `RecommendationLearningService` to compute
per-recommendation success rates. Only `eligible_for_learning=True` records
(improved and not_improved) contribute to the learning signal.

All classification logic is **deterministic**. Given the same input values,
`InterventionOutcomeService` must always produce the same outcome label. It does
not call any LLM, read from any external API, or vary by environment. LLM
judgment is explicitly prohibited for outcome classification — the reasons are the
same as for `interpret_kpi()`: reliability, testability, auditability, and the
guarantee that training labels are reproducible.

---

## 2. Key Constants

These values are defined at module level in `services/intervention_outcome_service.py`
and control the evaluation logic. Changes to any constant require this directive and the
unit tests to be updated first (directive → tests → code; see Section 9).

| Constant | Value | Meaning |
|---|---|---|
| `_HEALTHY_ACTIVITY_THRESHOLD` | `3` days | If `before_last_activity_days` is at or below this value, the student was already in a healthy state at trigger time. Improvement cannot be attributed to the intervention. |
| `_DEFAULT_WINDOW_DAYS` | `14` days | Default evaluation window length. `window_end = window_start + 14 days`. Outcomes become eligible for evaluation on or after `window_end`. |
| `_DEFAULT_MIN_DELTA` | `3` days | Minimum decrease in `last_activity_days` required to classify an outcome as `improved`. A delta below this threshold — even if positive — is classified as `not_improved`. |

---

## 3. Enrollment Lifecycle

### When enrollment occurs

`enroll()` is called by `MentorMessageService.process_trigger()` immediately after
`DeliverySucceeded` is written to `AI_ChatBot_TriggeredUsers`. It fires on both
the happy path (delivery succeeded) and the exception path (delivery failed).
The call is wrapped in a `try/except` — enrollment failure never propagates to
`process_trigger()`.

### Idempotency

Enrollment is idempotent. If a row with the same `cbm_id` already exists in
`AI_ChatBot_InterventionOutcomes`, `enroll()` returns the existing row without
modification. The UNIQUE constraint on `cbm_id` is enforced at both the
application layer (query-before-insert) and the database layer (unique index).

### Delivery gate

`delivery_gate_passed` is set at enrollment time:

| `delivery_succeeded` value | `delivery_gate_passed` |
|---|---|
| `True` | `True` — delivery confirmed; gate passes |
| `False` | `False` — delivery failed; gate does not pass |
| `None` | `False` — no delivery attempt was made; gate does not pass |

The distinction between `False` and `None` is intentional. Both prevent the
outcome from being attributed as a training example (eligible_for_learning will
be `False`). `None` does not imply failure — it means no attempt was recorded.

### Initial row state

Every enrolled row starts with:

| Column | Initial value |
|---|---|
| `outcome` | `"pending"` |
| `eligible_for_learning` | `None` — not yet evaluated |
| `window_start` | `TriggeredUsers.InsertDate` |
| `window_end` | `window_start + evaluation_window_days` |
| `evaluation_window_days` | Default: `14` |
| `before_last_activity_days` | Resolved from before-state (see Section 7) |
| `before_snapshot_source` | `"interpretation"`, `"trigger_data"`, or `"unavailable"` |

---

## 4. Evaluation Lifecycle

### When evaluation occurs

`evaluate_ready_outcomes()` is called by `OutcomeEvaluationWorker` on a 5-minute
poll loop. It queries for all rows where `outcome = 'pending' AND window_end <=
utcnow()`. For each matching record, `_evaluate_one()` is called with per-record
exception isolation — one record failing does not block others.

### Evaluation window rationale

A 14-day window is used because:
- Outcomes only become measurable after meaningful time has passed
- 14 days aligns with the stale-activity threshold used by `FingerprintGeneratorService`
  and `interpret_kpi()` — a consistent boundary across all three systems
- A 5-minute poll interval is more than sufficient given the 14-day minimum window

### After-state capture

At evaluation time, `_read_after_activity_days()` reads `TriggerData.LastActivityDays`
for the student. This is a **live read** at evaluation time — it reflects the
student's actual current state, not a frozen snapshot. If the student is no longer
in the system (no `TriggerData` row), the after-state is unavailable and the
outcome is classified as inconclusive.

### Delta computation

```
delta = before_last_activity_days - after_last_activity_days
```

A positive delta means the student's inactivity days decreased — they became more
active. A delta of zero or negative means no improvement or further disengagement.

---

## 5. The 4 Inconclusive Checks — Exact Priority Order

`_evaluate_one()` applies four inconclusive gate checks before any outcome
classification. They are evaluated in strict priority order. **The first matching
check sets the outcome and returns immediately.** Subsequent checks are not
evaluated once a match is found.

### Check 1 — Delivery gate not passed

```python
if not record.delivery_gate_passed:
    outcome = "inconclusive", eligible = False
    reason  = "Delivery did not succeed — intervention did not reach
               student; outcome not attributable"
```

**Rationale:** If the message was never delivered, any change in student activity
cannot be attributed to the intervention. Including such records in the training
set would corrupt the signal.

---

### Check 2 — Before-state unavailable

```python
if record.before_last_activity_days is None:
    outcome = "inconclusive", eligible = False
    reason  = f"Before-state unavailable (source: {before_snapshot_source})
               — baseline unknown"
```

**Rationale:** Without a before-state, a delta cannot be computed. The outcome
cannot be scored.

---

### Check 3 — Student already in healthy activity range at trigger time

```python
if record.before_last_activity_days <= _HEALTHY_ACTIVITY_THRESHOLD:  # <= 3
    outcome = "inconclusive", eligible = False
    reason  = f"Student was already in healthy activity range
               ({before_last_activity_days} days) at trigger time —
               activity KPI cannot signal improvement"
```

**Rationale:** The `last_activity_days` signal cannot detect improvement for a
student who was already active (≤3 days inactive). A student at 2 days cannot
improve to 0 days in a meaningful way that would reflect intervention success.
Including these records would bias success rates upward artificially.

---

### Check 4 — After-state unavailable

```python
if after_activity is None:
    outcome = "inconclusive", eligible = False
    reason  = "After-state unavailable at evaluation time —
               student may no longer be in system"
```

**Rationale:** Without an after-state, the delta cannot be computed. The student
may have left the system entirely.

---

### Outcome classification (if all 4 checks pass)

If none of the 4 inconclusive checks match, the outcome is classified by delta:

```python
delta = before_last_activity_days - after_last_activity_days

if delta >= minimum_delta_days:   # default: >= 3
    outcome = "improved",     eligible = True
else:
    outcome = "not_improved", eligible = True
```

Both `improved` and `not_improved` set `eligible_for_learning = True`. A student
who received the intervention and did not improve is as valuable a training
example as one who did improve — the learning system needs both labels.

---

## 6. `eligible_for_learning` Semantics

This column is a three-state flag, not a boolean. NULL, False, and True carry
distinct meanings and must never be collapsed.

| Value | Meaning | When set |
|---|---|---|
| `NULL` | Pending — not yet evaluated | Set at enrollment; remains NULL until `_evaluate_one()` runs |
| `False` | Inconclusive — non-trainable | Set by any of the 4 inconclusive checks; this record must never enter the training set |
| `True` | Trainable outcome — improved or not_improved | Set only after all 4 inconclusive checks pass; this record contributes to success rate computation |

**Critical rule:** Only rows where `eligible_for_learning = True` are used by
`RecommendationLearningService.get_success_rates()`. Rows where
`eligible_for_learning = False` or `NULL` must never be included in success
rate queries.

**Why NULL instead of False for pending?** NULL preserves the distinction
between "not yet evaluated" and "evaluated but inconclusive." A query filtering
`eligible_for_learning IS NULL` retrieves only unevaluated rows; filtering
`eligible_for_learning = False` retrieves only inconclusive evaluated rows.
These two populations are operationally distinct.

---

## 7. Before-State Resolution Priority

`_resolve_before_state()` is called at enrollment time to capture a snapshot of
the student's state before the intervention takes effect. Three sources are tried
in priority order. The first source that yields a `last_activity_days` value is
used; the others are not attempted.

### Priority 1 — `AIInterpretation.source_snapshot_json` (preferred)

Queries for the most recent active `AIInterpretation` for the student created at
or before `window_start`. If found, attempts to extract `last_activity_days` from
the stored JSON payload using `_extract_activity_days_from_snapshot()`.

- `before_snapshot_source` = `"interpretation"`
- `interpretation_id` is populated
- **Why preferred:** The interpretation snapshot is immutable — it was frozen at
  AI call time and cannot change retroactively. This is the most reliable baseline.

### Priority 2 — `TriggerData.LastActivityDays` (live fallback)

Queries the current `TriggerData` row for the student.

- `before_snapshot_source` = `"trigger_data"`
- **Why used as fallback:** `TriggerData` is a live table. The value at enrollment
  time reflects the student's current state, not necessarily the state at trigger
  time. This fallback is acceptable when no interpretation snapshot is available,
  but it carries more uncertainty.

### Priority 3 — `'unavailable'` (no source found)

Neither source returned a usable value.

- `before_snapshot_source` = `"unavailable"`
- `before_last_activity_days` = `None`
- This record will be classified as inconclusive at evaluation time (Check 2)

---

## 8. Snapshot Parsing — Two Shape Contract

`_extract_activity_days_from_snapshot()` handles two JSON payload shapes produced
by the orchestration layer. Both must be supported; neither takes precedence —
Shape A is tried first because the flat `kpis` list is faster to traverse.

### Shape A — flat KPI list (orchestration payload)

```json
{
  "kpis": [
    {"kpi_name": "last_activity_days", "value": 18}
  ]
}
```

Search path: `data["kpis"][*]["kpi_name"] == "last_activity_days"` → `["value"]`

### Shape B — nested dimensions/signals (extraction payload)

```json
{
  "dimensions": {
    "engagement": {
      "signals": [
        {"name": "last_activity_days", "value": 18}
      ]
    }
  }
}
```

Search path: `data["dimensions"][*]["signals"][*]["name"] == "last_activity_days"` → `["value"]`

If neither shape yields a value, `None` is returned. Invalid JSON or a missing
`value` field are handled without raising — the function returns `None`.

---

## 9. Rules

### Determinism is mandatory

`_evaluate_one()` must produce the same outcome label for the same input state.
It reads from `TriggerData` and `AIInterpretation` — these reads are live DB reads,
not random sources. Given the same DB state at evaluation time, the output is
deterministic. No LLM, random seed, timestamp beyond `window_end`, or environment
variable may affect the classification outcome.

**LLM judgment is prohibited for outcome classification.** The training labels
produced by this service feed directly into `RecommendationLearningService`'s
success rate computation. Labels that vary based on LLM inference would corrupt
the learning signal with non-reproducible noise. Any proposal to use LLM judgment
for outcome classification is rejected by this directive.

### Defensive contract is mandatory

All public methods (`enroll`, `evaluate_ready_outcomes`) must be non-fatal. Any
exception within these methods must be caught, logged, and swallowed. The caller
must never receive an exception from `InterventionOutcomeService`. This rule
exists because both methods are called as non-blocking side effects of
`process_trigger()` — a failure in outcome tracking must never affect message
delivery.

### Threshold and rule changes require this directive and tests to be updated first

The constants in Section 2 and the priority order in Section 5 represent
deliberate business decisions. Before changing any value or reordering any check:

1. Update this directive with the new value and the business rationale
2. Update or add unit tests in `tests/unit/test_intervention_outcome_service.py`
   to cover the new boundary or behaviour
3. Only then update the constants or logic in `services/intervention_outcome_service.py`

Definition of done for a threshold change: directive updated → tests updated and
passing → code updated.

### Adding a new inconclusive check

If a new inconclusive condition is identified:
1. Document it in Section 5 with its position in the priority order and the business
   rationale for that position
2. Write unit tests covering the new check and verifying it does not fire for cases
   that should pass through to classification
3. Implement the check in `_evaluate_one()` at the correct priority position
4. Do not reorder existing checks without updating this directive and all affected tests

---

## 10. Edge Cases

| Condition | Behaviour |
|---|---|
| `enroll()` called twice for the same `cbm_id` | Returns existing row; no insert; no modification to any field |
| `user_id` is `None` | `_resolve_before_state()` returns immediately with `before_snapshot_source='unavailable'`; outcome will be inconclusive at Check 2 |
| `delivery_succeeded` is `None` | Treated as `False`; `delivery_gate_passed=False`; inconclusive at Check 1 |
| `before_last_activity_days = 3` (exactly at threshold) | Check 3 fires (`<= 3` is inclusive); inconclusive |
| `before_last_activity_days = 4` | Check 3 does not fire; proceeds to after-state capture |
| `delta = 3` (exactly at minimum) | `3 >= 3` → improved, eligible=True |
| `delta = 2` | `2 < 3` → not_improved, eligible=True |
| `delta = 0` (no change) | not_improved, eligible=True |
| `delta < 0` (student became less active) | not_improved, eligible=True |
| `AIInterpretation` found but snapshot has no `last_activity_days` | Falls through to Priority 2 (`TriggerData`) |
| `TriggerData` row not found for user | Priority 2 fails; falls through to `'unavailable'` |
| `after_activity` read fails with an exception | `_read_after_activity_days()` swallows exception, returns `None`; Check 4 fires |
| `evaluate_ready_outcomes()` query fails | Returns 0; logs error; no records updated |
| One record fails inside `evaluate_ready_outcomes()` | Per-record exception isolation; other records continue evaluating |

---

## 11. Verification Requirements

Tests live in `tests/unit/test_intervention_outcome_service.py`.

The test suite must cover:

| Coverage requirement | Description |
|---|---|
| Enrollment happy path | `enroll()` creates a row with correct field values for a new `cbm_id` |
| Idempotent enrollment | Second call for same `cbm_id` returns existing row; count remains 1 |
| Delivery gate: `True` | `delivery_succeeded=True` → `delivery_gate_passed=True` |
| Delivery gate: `False` | `delivery_succeeded=False` → `delivery_gate_passed=False` |
| Delivery gate: `None` | `delivery_succeeded=None` → `delivery_gate_passed=False` |
| Before-state: interpretation source | Priority 1 succeeds → `before_snapshot_source="interpretation"` |
| Before-state: trigger_data fallback | Priority 1 fails, Priority 2 succeeds → `before_snapshot_source="trigger_data"` |
| Before-state: unavailable | Both Priority 1 and 2 fail → `before_snapshot_source="unavailable"` |
| Snapshot Shape A parsing | `{"kpis": [{"kpi_name": "last_activity_days", "value": N}]}` → returns N |
| Snapshot Shape B parsing | `{"dimensions": {…}}` nested format → returns N |
| Check 1: delivery gate not passed | `delivery_gate_passed=False` → inconclusive, eligible=False |
| Check 2: before-state None | `before_last_activity_days=None` → inconclusive, eligible=False |
| Check 3: student already healthy | `before_last_activity_days <= 3` → inconclusive, eligible=False |
| Check 3: boundary — exactly 3 | `before_last_activity_days=3` → inconclusive (inclusive boundary) |
| Check 3: boundary — exactly 4 | `before_last_activity_days=4` → proceeds to after-state capture |
| Check 4: after-state unavailable | `after_activity=None` → inconclusive, eligible=False |
| improved: delta exactly at threshold | `delta=3`, `minimum_delta_days=3` → improved, eligible=True |
| improved: delta above threshold | `delta=10` → improved, eligible=True |
| not_improved: delta below threshold | `delta=2` → not_improved, eligible=True |
| not_improved: delta zero | `delta=0` → not_improved, eligible=True |
| not_improved: delta negative | Student became less active → not_improved, eligible=True |
| `eligible_for_learning` NULL at enrollment | Every new row must have `eligible_for_learning=None` |
| Priority order: Check 1 fires before Check 2 | Even if before-state is also None, delivery gate check fires first |
| `enroll()` failure absorbed | Exception in enroll → returns None; does not raise |
| `evaluate_ready_outcomes()` per-record isolation | One record failing does not block others from evaluating |

Run with:

```
pytest tests/unit/test_intervention_outcome_service.py tests/unit/test_outcome_evaluation_worker.py -v
```

Current result: **66 passed** (test_intervention_outcome_service) + **6 passed** (test_outcome_evaluation_worker) as of 2026-05-29.

---

## 12. Code Map

| Responsibility | File |
|---|---|
| Enrollment + evaluation service | `services/intervention_outcome_service.py` |
| ORM model | `services/models.py` → `InterventionOutcome` |
| Alembic migration | `alembic/versions/0012_add_intervention_outcomes_table.py` |
| Evaluation poll worker | `services/worker/outcome_evaluation_worker.py` |
| Long-running worker loop | `services/worker/run_outcome_evaluation_worker.py` |
| Enrollment call site | `services/mentor_message_service.py` → `process_trigger()` |
| Unit tests — service | `tests/unit/test_intervention_outcome_service.py` |
| Unit tests — worker | `tests/unit/test_outcome_evaluation_worker.py` |
| E2E tests | `tests/e2e/test_outcome_learning_flow.py` |
| Related directive (fingerprint thresholds) | `directives/behavior_fingerprint_contract.md` |
| Related directive (KPI interpretation thresholds) | `directives/kpi_interpretation_contract.md` |
| Related directive (mentor message delivery) | `directives/ai_mentor_message_contract.md` |

---

## 13. Definition of Done

- [x] `InterventionOutcomeService` implemented in `services/intervention_outcome_service.py`
- [x] `InterventionOutcome` ORM model in `services/models.py`
- [x] Alembic migration `0012_add_intervention_outcomes_table.py` written
- [x] Evaluation worker implemented (`outcome_evaluation_worker.py`, `run_outcome_evaluation_worker.py`)
- [x] Enrollment wired into `mentor_message_service.py` — both happy and exception paths
- [x] Unit tests exist and pass (66 + 6 = 72 tests as of 2026-05-29)
- [x] E2E tests written; fixture errors corrected for SQL Server
- [x] This directive exists at `directives/intervention_outcome_contract.md`
- [x] All 4 inconclusive checks documented with exact priority order and business rationale
- [x] `eligible_for_learning` three-state semantics documented (NULL / False / True)
- [x] Before-state resolution priority documented (interpretation → trigger_data → unavailable)
- [x] Snapshot parsing two-shape contract documented (Shape A and Shape B)
- [x] Determinism requirement and LLM prohibition documented
- [x] Threshold-change process documented
- [ ] Migration 0012 applied to SQL Server (`alembic upgrade head`)
- [ ] E2E tests run against real SQL Server and pass
- [ ] A junior developer can read this directive and understand exactly how outcomes are enrolled, classified, and labeled for the learning system
