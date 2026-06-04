# Directive: Recommendation Learning Contract

## 1. Purpose

This directive covers two services that together form the recommendation learning
pipeline:

**`RecommendationTrackingService`** records every AI-generated recommendation
delivered to a student and allows those records to be invalidated when the
recommendation becomes stale. It answers:

> What recommendations have we made for this student, and are they still active?

**`RecommendationLearningService`** reads those records and the outcomes produced
by `InterventionOutcomeService` to compute which recommendation strategies work
best. It answers:

> Which recommendation types lead to improved student engagement, and with what
> confidence?

Together they form a closed feedback loop: recommendations are tracked at delivery
time → outcomes are evaluated after a 14-day window → success rates are computed
per recommendation key → rankings are returned to the caller for use in future
recommendations.

All computation in both services is **deterministic**. Given the same database
state, both services must always return the same result. Neither service calls any
LLM, external API, or random source. LLM-based ranking is explicitly prohibited —
see Section 9.

---

## 2. Key Constants

| Constant | Value | Location | Meaning |
|---|---|---|---|
| `min_sample` default | `10` | `get_success_rates()` / `get_ranked_keys()` parameter default | Minimum eligible outcomes before a key's success rate is considered statistically reliable |

The `min_sample=10` default is a parameter, not a module-level constant — callers
may override it. Changes to the default require this directive and the unit tests
to be updated first (directive → tests → code; see Section 9).

---

## 3. RecommendationTrackingService — `record()` Lifecycle

### When `record()` is called

`record()` is called by `MentorMessageService.process_trigger()` immediately after
`InterventionOutcomeService().enroll()` on both the happy path (delivery
succeeded) and the delivery-failed path. The call is wrapped in a `try/except` —
tracking failure never propagates to `process_trigger()`.

### Parameters

| Parameter | Type | Notes |
|---|---|---|
| `cbm_id` | int | PK of the `TriggeredUsers` row being tracked |
| `interpretation_id` | int or None | FK to `AIInterpretation` if one existed at trigger time |
| `entity_id` | str | The student identifier |
| `recommendation_type` | str | Broad action category — display only, not used as a learning signal |
| `recommendation_key` | str | Granular learning identifier — primary grouping key for success rates |
| `recommendation_text` | str | Human-readable recommendation text |
| `dimension` | str | Sentinel dimension the recommendation addresses |
| `risk_level` | str | Student risk level at trigger time |
| `confidence` | float | AI confidence score at trigger time |
| `recommendation_context` | dict | Frozen snapshot of student state at trigger time; serialized to JSON |
| `generated_by` | str | Source identifier (e.g., `"MentorMessageService"`) |
| `model_name` | str or None | Optional AI model identifier |

### Idempotency check

Before inserting, `record()` queries for an existing row matching:

```python
cbm_id == cbm_id
AND recommendation_key == recommendation_key
AND is_active == True
```

If a matching active row is found, it is returned immediately without any insert
or commit. **Invalidated rows (`is_active=False`) do not match this check** — a
new row may be inserted after invalidation.

### Insert and return

If no active match is found, a new `Recommendation` row is inserted with
`is_active=True`. The row is committed and refreshed before returning.

### Failure handling

On any exception: log at WARNING level, attempt `db.rollback()`, return `None`.
Callers must treat `None` as a non-fatal tracking gap, not an error.

---

## 4. RecommendationTrackingService — `invalidate()` Lifecycle

### When `invalidate()` is called

`invalidate()` is called when a recommendation is no longer valid — for example,
when a student's state has materially changed and the original recommendation no
longer applies.

### Behaviour

1. Query for active row: `cbm_id == cbm_id AND recommendation_key == recommendation_key AND is_active == True`
2. If no matching row: return immediately (no-op — not an error)
3. If row found: set `is_active=False`, `invalidated_at=datetime.utcnow()`, `invalidation_reason=reason`; commit

### Rows are never deleted

`invalidate()` soft-disables rows. Rows are never physically deleted from
`AI_ChatBot_Recommendations`. Invalidated rows preserve the audit history of
recommendations that were made and then superseded.

### Failure handling

On any exception: log at WARNING level, attempt rollback, return without
side-effects. Callers are never affected.

---

## 5. Idempotency and Active/Invalidated State

The idempotency contract for `record()` is **key-and-active-status scoped**, not
key-only. This is a deliberate design decision distinct from
`InterventionOutcomeService`, which is idempotent on `cbm_id` alone.

| Scenario | `record()` result |
|---|---|
| No row exists for `(cbm_id, recommendation_key)` | Inserts new row |
| Active row exists for `(cbm_id, recommendation_key)` | Returns existing row; no insert |
| Only invalidated row(s) exist for `(cbm_id, recommendation_key)` | Inserts new row; invalidated rows do not block insert |
| Exception during query or insert | Returns None; rollback attempted |

**Why active-status scoping?** A recommendation may be made, then invalidated
when a student's situation changes, then re-recommended after a new trigger fires.
Each re-recommendation is a distinct event and produces a new row linked to the
new `cbm_id`. Blocking all future records because an invalidated row exists would
prevent the system from tracking repeated recommendation attempts.

---

## 6. `recommendation_key` and `recommendation_type` Contract

### `recommendation_type` — display only

`recommendation_type` is the broad action category. Examples: `"reach_out"`,
`"deadline_reminder"`. It is stored and returned in success rate output for
display purposes. **It is never used as a grouping key for learning.** Two
recommendations with the same type but different keys are treated as distinct
learning signals.

### `recommendation_key` — primary learning identifier

`recommendation_key` is the granular identifier used for grouping, ranking, and
success rate computation. Examples: `"reach_out_high"`, `"deadline_reminder_low"`.

### Derivation convention in `MentorMessageService`

The current call site derives `recommendation_key` as:

```python
f"{trigger_type}_{trigger_level}".lower().replace(" ", "_")
```

Falls back to `"unknown"` when either `trigger_type` or `trigger_level` is absent.

The frozen context dict passed to `recommendation_context` at the call site is:

```python
{
    "trigger_type":  trigger_type,
    "trigger_level": trigger_level,
    "kpi":           trigger_kpi,
    "severity":      trigger_severity,
}
```

**This derivation pattern is a caller convention, not enforced by
`RecommendationTrackingService` itself.** The service accepts any non-empty
string as `recommendation_key`. If the derivation pattern changes, this directive
must be updated before the code changes.

---

## 7. `_SafeEncoder` Serialization Priority

`_SafeEncoder` is a `json.JSONEncoder` subclass. When `json.dumps` encounters a
value that the default encoder cannot handle, `_SafeEncoder.default()` is called
with that value. The conversion priority is:

| Priority | Type check | Output |
|---|---|---|
| 1 | `isinstance(obj, datetime)` | ISO-8601 string via `obj.isoformat()` |
| 2 | `isinstance(obj, Decimal)` | `float(obj)` |
| 3 | Anything else | `str(obj)` — preserves the value as a string rather than discarding it |
| Fallback | `str(obj)` itself raises | `"<unserializable>"` — caught by inner try/except |

`_serialize_context()` wraps `json.dumps` with `_SafeEncoder`. If `json.dumps`
itself raises (e.g., circular reference in the dict), the entire call fails and
`_serialize_context()` returns `"{}"`, logging a WARNING. This fallback is always
logged — a silent `"{}"` stored in the DB indicates a serialization failure, not
an empty context.

**Why preserve rather than discard?** The context is stored as NOT NULL in the
schema. Silently discarding non-serializable values would produce a valid JSON
string that misrepresents the actual context passed at tracking time. Preserving
values as strings keeps the context meaningful for audit and debugging.

---

## 8. RecommendationLearningService — `success_rate` Formula

`get_success_rates()` joins `AI_ChatBot_Recommendations` to
`AI_ChatBot_InterventionOutcomes` on `cbm_id`. The join produces one row per
`(recommendation_key, cbm_id)` pair. Rows are then aggregated by
`recommendation_key`.

### Eligibility filters (applied before aggregation)

| Filter | Value | Rationale |
|---|---|---|
| `InterventionOutcome.eligible_for_learning` | `== True` | Inconclusive outcomes carry no signal; including them would dilute the rate |
| `Recommendation.is_active` | `== True` | Invalidated recommendations are excluded — they represent superseded advice |
| `Recommendation.dimension` | optional | Restrict to a specific Sentinel dimension |
| `Recommendation.risk_level` | optional | Restrict to a specific student risk level |

### Aggregation

```
total_eligible = COUNT(InterventionOutcome.id)       -- eligible outcomes linked to this key
total_improved = SUM(CASE WHEN outcome='improved' THEN 1 ELSE 0 END)
```

### `success_rate` computation

```
success_rate = total_improved / total_eligible   when total_eligible > 0
success_rate = None                              when total_eligible = 0
```

`None` means no labeled outcomes exist yet for this key — the rate is unknown,
not zero. A `success_rate` of `0.0` means labeled outcomes exist but none resulted
in improvement.

### `has_sufficient_sample`

```
has_sufficient_sample = total_eligible >= min_sample   (default min_sample = 10)
```

A key can have a non-None `success_rate` and still have `has_sufficient_sample=False`
if it has fewer than `min_sample` eligible outcomes. Callers must not treat an
insufficient-sample rate as statistically reliable.

### `recommendation_type` in output

`recommendation_type` is included in the output dict for display purposes only.
It is not used in any computation and must never be used as a grouping or ranking
signal by callers.

---

## 9. Ranking Algorithm — `get_ranked_keys()`

`get_ranked_keys()` accepts a list of candidate `recommendation_key` strings and
returns them sorted by descending success rate, with insufficient-sample candidates
appended after.

### Step-by-step algorithm

1. Call `get_success_rates(db, dimension=dimension, risk_level=risk_level, min_sample=min_sample)`
2. Build a lookup of sufficient-sample keys to their success rate:
   ```python
   ranked_lookup = {
       r["recommendation_key"]: r["success_rate"]
       for r in rates
       if r["has_sufficient_sample"]
   }
   ```
3. **Ranked group:** candidates that appear in `ranked_lookup`, sorted by
   `success_rate` descending:
   ```python
   ranked = sorted([k for k in candidates if k in ranked_lookup],
                   key=lambda k: ranked_lookup[k], reverse=True)
   ```
4. **Unranked group:** candidates not in `ranked_lookup`, in their original
   input order:
   ```python
   unranked = [k for k in candidates if k not in ranked_lookup]
   ```
5. Return `ranked + unranked`

### No-candidate-dropped guarantee

Every candidate supplied to `get_ranked_keys()` appears exactly once in the
returned list. A candidate with no data or insufficient data is never removed —
it is moved to the unranked group and returned in its original position relative
to other unranked candidates.

**Why this guarantee exists:** The caller uses the ranked list to select which
recommendation to present next. Silently dropping a candidate could cause the
system to never recommend a strategy that simply lacks historical data — starving
that option of the outcome data it needs to ever become rankable.

### Tie-breaking

Candidates with equal `success_rate` values are ordered by Python's stable sort,
which preserves their relative input order. No secondary sort key is applied.

---

## 10. Rules

### Determinism is mandatory

Given the same database state at query time, both services must return the same
result. `get_success_rates()` is a pure SQL aggregation — it is deterministic by
construction. `get_ranked_keys()` depends entirely on `get_success_rates()` and
Python's stable sort — also deterministic.

**LLM-based ranking is explicitly prohibited.** The rankings produced by
`get_ranked_keys()` feed into recommendation selection logic. If rankings varied
across calls due to LLM inference, the learning signal would be non-reproducible:
a recommendation's observed success rate would depend in part on how often it was
presented, which would depend on non-deterministic rankings, creating a corrupted
feedback loop. Deterministic ranking from observed outcome data is the only
acceptable approach.

### Defensive contract is mandatory for both services

All public methods in both services must be non-fatal:
- `RecommendationTrackingService.record()` → returns `None` on exception
- `RecommendationTrackingService.invalidate()` → returns without side-effects on exception
- `RecommendationLearningService.get_success_rates()` → returns `[]` on exception
- `RecommendationLearningService.get_ranked_keys()` → returns original candidate list on exception

This contract exists because both services are called as non-blocking side effects.
A failure in tracking or learning must never affect `process_trigger()` outcomes
or the delivery pipeline.

### Changes to `min_sample` default require directive and tests first

The `min_sample=10` default is a business decision — it determines how much
evidence is required before a success rate is treated as statistically reliable.
Before changing this value:

1. Update this directive with the new value and business rationale
2. Update or add tests in `tests/unit/test_recommendation_learning_service.py`
   covering the new boundary
3. Only then update the parameter default in `recommendation_learning_service.py`

### Changes to `_SafeEncoder` priority order require directive first

The serialization priority in Section 7 is a documented contract. If a new type
needs special handling, add it to this directive (with rationale) before adding
it to `_SafeEncoder.default()`.

### Changes to `recommendation_key` derivation require directive first

The derivation pattern `f"{trigger_type}_{trigger_level}".lower().replace(" ", "_")`
is documented in Section 6. Any change to the pattern must be reflected here
before the code is changed — the pattern affects all historical grouping and
ranking results.

---

## 11. Edge Cases

| Condition | Behaviour |
|---|---|
| `record()` called twice for same `(cbm_id, recommendation_key)` while active | Returns existing row; no duplicate inserted |
| `record()` called after `invalidate()` for same `(cbm_id, recommendation_key)` | Inserts new row; invalidated row does not block |
| `invalidate()` called when no active row exists | No-op — returns immediately |
| `recommendation_context` contains a `datetime` value | `_SafeEncoder` converts to ISO-8601 string |
| `recommendation_context` contains a `Decimal` value | `_SafeEncoder` converts to float |
| `recommendation_context` contains a non-serializable type | `_SafeEncoder` converts to `str(obj)` |
| `recommendation_context` causes circular reference in JSON | `_serialize_context()` catches exception; stores `"{}"` with WARNING log |
| `get_success_rates()` called with no eligible outcomes in DB | Returns `[]` |
| `get_success_rates()` called for a key with `total_eligible=0` | That key does not appear in results (no row in aggregation) |
| `get_ranked_keys()` called with a candidate not in the DB at all | Candidate appears in unranked group in its original position |
| `get_ranked_keys()` called with a candidate with insufficient sample | Candidate appears in unranked group; rate exists but is not used for ranking |
| Two candidates have equal `success_rate` | Stable sort preserves original input order between tied candidates |
| `get_success_rates()` raises an exception | Returns `[]` |
| `get_ranked_keys()` raises an exception | Returns `list(candidates)` — a copy of the original input |
| `trigger_type` is None at `recommendation_key` derivation | Derivation falls back to `"unknown"` |
| `trigger_level` is None at `recommendation_key` derivation | Derivation falls back to `"unknown"` |

---

## 12. Verification Requirements

### `RecommendationTrackingService` tests (`tests/unit/test_recommendation_tracking_service.py`)

| Coverage requirement | Description |
|---|---|
| `record()` happy path | New row inserted with correct field values; `is_active=True` |
| `record()` idempotency — active row | Second call returns existing row; no new insert |
| `record()` after invalidation | New row inserted after prior row is invalidated |
| `invalidate()` — row found | `is_active=False`, `invalidated_at` stamped, `invalidation_reason` stored |
| `invalidate()` — no active row | No-op; no exception |
| `_SafeEncoder` — `datetime` | ISO-8601 string output |
| `_SafeEncoder` — `Decimal` | float output |
| `_SafeEncoder` — arbitrary type | `str()` output |
| `_serialize_context()` — valid dict | Returns valid JSON string |
| `_serialize_context()` — catastrophic failure | Returns `"{}"` with log |
| `record()` failure absorbed | Exception → returns `None`; does not raise |
| `record()` rollback | `db.rollback()` called on exception |
| `is_active` defaults True | Newly created row has `is_active=True` |

### `RecommendationLearningService` tests (`tests/unit/test_recommendation_learning_service.py`)

| Coverage requirement | Description |
|---|---|
| `get_success_rates()` — eligible filter | Only `eligible_for_learning=True` rows counted |
| `get_success_rates()` — active filter | Only `is_active=True` recommendations included |
| `get_success_rates()` — success_rate formula | `total_improved / total_eligible` correct |
| `get_success_rates()` — `success_rate=None` | When `total_eligible=0`, rate is None |
| `get_success_rates()` — `has_sufficient_sample=True` | When `total_eligible >= min_sample` |
| `get_success_rates()` — `has_sufficient_sample=False` | When `total_eligible < min_sample` |
| `get_success_rates()` — dimension filter | Optional filter restricts results correctly |
| `get_success_rates()` — exception fallback | Returns `[]` on DB error |
| `get_ranked_keys()` — sufficient-sample ranked first | Key with rate=1.0 before key with rate=0.0 |
| `get_ranked_keys()` — unranked appended in original order | Insufficient-sample candidates preserve input order |
| `get_ranked_keys()` — no candidates dropped | Every input candidate appears in output |
| `get_ranked_keys()` — tied rates | Stable sort preserves input order between ties |
| `get_ranked_keys()` — exception fallback | Returns copy of original candidate list |
| `get_ranked_keys()` — unknown candidate (not in DB) | Appears in unranked group |

Run with:

```
pytest tests/unit/test_recommendation_tracking_service.py tests/unit/test_recommendation_learning_service.py -v
```

Current result: **32 passed** (tracking) + **29 passed** (learning) = **61 passed, 0 failed** as of 2026-05-30.

---

## 13. Code Map

| Responsibility | File |
|---|---|
| Tracking service | `services/recommendation_tracking_service.py` |
| Learning service | `services/recommendation_learning_service.py` |
| `Recommendation` ORM model | `services/models.py` → `Recommendation` (model #15) |
| Alembic migration | `alembic/versions/0013_add_recommendations_table.py` |
| `recommendation_key` derivation call site | `services/mentor_message_service.py` → `process_trigger()` |
| Unit tests — tracking | `tests/unit/test_recommendation_tracking_service.py` |
| Unit tests — learning | `tests/unit/test_recommendation_learning_service.py` |
| E2E tests | `tests/e2e/test_recommendation_learning_flow.py` |
| Related directive (outcome labeling) | `directives/intervention_outcome_contract.md` |
| Related directive (mentor message delivery) | `directives/ai_mentor_message_contract.md` |

---

## 14. Definition of Done

- [x] `RecommendationTrackingService` implemented in `services/recommendation_tracking_service.py`
- [x] `RecommendationLearningService` implemented in `services/recommendation_learning_service.py`
- [x] `Recommendation` ORM model in `services/models.py`
- [x] Alembic migration `0013_add_recommendations_table.py` written
- [x] `record()` and `invalidate()` wired into `mentor_message_service.py` — both delivery paths
- [x] Unit tests exist and pass (32 + 29 = 61 tests as of 2026-05-30)
- [x] E2E tests written and skipping cleanly (`test_recommendation_learning_flow.py` — 7 tests)
- [x] This directive exists at `directives/recommendation_learning_contract.md`
- [x] `(cbm_id, recommendation_key)` idempotency rule documented with active-status scoping
- [x] `_SafeEncoder` priority order documented (datetime → ISO-8601, Decimal → float, anything → str)
- [x] `success_rate` formula documented (`total_improved / total_eligible`, None when 0)
- [x] `min_sample=10` documented with change process
- [x] Ranking algorithm documented step-by-step
- [x] No-candidate-dropped guarantee documented with rationale
- [x] Failure fallbacks documented for all four public methods
- [x] Determinism requirement and LLM prohibition documented
- [ ] Migration 0013 applied to SQL Server (`alembic upgrade head`)
- [ ] E2E tests run against real SQL Server and pass
- [ ] A junior developer can read this directive and understand exactly how recommendations are tracked, how success rates are computed, and why rankings are deterministic
