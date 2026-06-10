# Directive: Adaptive Recommendation Contract

## 1. Purpose

`AdaptiveRecommendationService` solves one problem: **the mechanical `recommendation_key`
derivation in `MentorMessageService` cannot improve over time**. The current fallback
formula `f"{trigger_type}_{trigger_level}".lower()` always produces the same key for a
given trigger context, regardless of which recommendation strategies have historically
worked best for similar students.

This service replaces that derivation with **evidence-driven, governance-controlled
selection**. Given a trigger context, it:

1. Reads a pool of candidate `recommendation_key` values from
   `AI_ChatBot_RecommendationCandidatePools` — defined by governance operators
2. Ranks those candidates by historical success rate via `RecommendationLearningService`
3. Selects the best candidate most of the time (exploitation), with a small probability
   of random selection (exploration) to accumulate outcome data on less-tried strategies
4. Returns the selected key so that `RecommendationTrackingService` records it and
   outcome learning can attribute future results to it

When no pool is configured for a trigger context, the caller-supplied `fallback_key` is
returned unchanged — the system degrades gracefully to the previous mechanical behavior.

All ranking logic is **deterministic given the same database state**. LLM-based
recommendation selection is explicitly prohibited — see Section 9.

---

## 2. Key Constants

| Constant | Value | Meaning |
|---|---|---|
| `_DEFAULT_EPSILON` | `0.05` | System-wide exploration probability when `epsilon_override` is NULL |
| `_DEFAULT_MIN_SAMPLE` | `10` | System-wide minimum eligible outcomes for ranking eligibility when `min_sample_override` is NULL |

Both constants are defined at module level in
`services/adaptive_recommendation_service.py`. Changes require this directive and the
unit tests to be updated first (directive → tests → code; see Section 9).

---

## 3. `select_key()` — Full Contract

### Signature

```python
def select_key(
    self,
    db: Session,
    trigger_type: str,
    dimension: str,
    risk_level: Optional[str],
    fallback_key: str,
) -> str:
```

### Parameters

| Parameter | Type | Notes |
|---|---|---|
| `db` | `Session` | SQLAlchemy session — read-only use; no commits or rollbacks issued |
| `trigger_type` | `str` | Matches `RecommendationCandidatePool.trigger_type` for pool lookup |
| `dimension` | `str` | Matches `RecommendationCandidatePool.dimension`; also forwarded to `get_ranked_keys()` |
| `risk_level` | `Optional[str]` | Forwarded to `get_ranked_keys()` as a success-rate filter; `None` means no filter |
| `fallback_key` | `str` | Returned unchanged on any failure or when no pool exists |

### Return value

Always returns a non-empty `str`. The returned string is either a `recommendation_key`
from the pool's candidate list, or `fallback_key`. This method **never raises**.

### Session contract

`select_key()` uses the session for read-only queries only. It does not call
`db.commit()`, `db.add()`, or `db.rollback()`. The caller may safely share the session
with subsequent write operations (e.g., `RecommendationTrackingService.record()`).

---

## 4. Candidate Pool Lookup

### Query

```
SELECT * FROM AI_ChatBot_RecommendationCandidatePools
WHERE trigger_type = :trigger_type
  AND dimension    = :dimension
  AND is_active    = True
LIMIT 1
```

The composite UNIQUE constraint on `(trigger_type, dimension)` guarantees at most one
active row per context.

### Lookup outcomes

| Result | Behaviour |
|---|---|
| Row found, `is_active=True` | Continue to candidate parsing |
| No row found | Return `fallback_key` immediately — silent, no log |
| Row exists but `is_active=False` | Excluded by the filter; treated as "no row found" |

**No pool found is not an error.** A missing pool is the expected state for any
`(trigger_type, dimension)` pair that has not yet been configured by a governance
operator. The system falls back to `fallback_key` without any warning log.

---

## 5. `candidate_keys_json` Requirements

`candidate_keys_json` is a NOT NULL `TEXT` column in `AI_ChatBot_RecommendationCandidatePools`.
The service layer is solely responsible for JSON serialization and deserialization.
Raw text must never be stored directly.

### Valid format

A JSON array of `recommendation_key` strings in the governance operator's preferred
default priority order:

```json
["attendance_personal_outreach", "attendance_deadline_reminder", "attendance_cohort_comparison"]
```

The minimum valid value is `'[]'` (empty array, encoded as a string).

### Parsing behavior

| `candidate_keys_json` value | Parsed result | Behaviour |
|---|---|---|
| `'["key_a", "key_b"]'` | `["key_a", "key_b"]` | Normal flow continues |
| `'[]'` | `[]` | WARNING logged; `fallback_key` returned |
| `None` | Coerced to `'[]'` via `or "[]"` guard | WARNING logged; `fallback_key` returned |
| Malformed JSON | `json.JSONDecodeError` caught | WARNING logged; `fallback_key` returned |

**Why empty pool triggers WARNING:** An empty `candidate_keys_json` stored on an active
pool row is a governance misconfiguration — the operator created a pool but did not
populate it. This is distinct from "no pool found" (expected) and therefore warrants a
WARNING log to signal the configuration gap.

---

## 6. Per-Pool Parameter Resolution

After the pool row is retrieved, two adaptive parameters are resolved:

### `epsilon` — exploration probability

```python
epsilon = pool.epsilon_override if pool.epsilon_override is not None else _DEFAULT_EPSILON
```

| `pool.epsilon_override` | Effective epsilon |
|---|---|
| `None` | `0.05` (system default) |
| `0.01` | `0.01` — low exploration for high-stakes contexts |
| `0.20` | `0.20` — higher exploration for contexts with many untried candidates |

### `min_sample` — minimum outcomes for ranking eligibility

```python
min_sample = pool.min_sample_override if pool.min_sample_override is not None else _DEFAULT_MIN_SAMPLE
```

| `pool.min_sample_override` | Effective min_sample |
|---|---|
| `None` | `10` (system default) |
| `5` | `5` — rank candidates with fewer outcomes |
| `20` | `20` — require more evidence before ranking |

`min_sample` is forwarded directly to `RecommendationLearningService.get_ranked_keys()`.
It controls whether a candidate's success rate is considered `has_sufficient_sample=True`.
Only sufficient-sample candidates appear in the ranked group; the rest are appended in
original candidate order.

---

## 7. Epsilon-Greedy Algorithm

### Step-by-step

```
1. RANK
   ranked = RecommendationLearningService().get_ranked_keys(
       db, candidates, dimension=dimension, risk_level=risk_level, min_sample=min_sample
   )
   On exception: get_ranked_keys() returns list(candidates) — ranked[0] == candidates[0]

2. DRAW
   draw = random.random()

3. SELECT
   if draw < epsilon:
       return random.choice(candidates)   # exploration
   else:
       return ranked[0]                   # exploitation
```

### Exploitation (`draw >= epsilon`)

Returns `ranked[0]` — the candidate with the highest success rate that has sufficient
outcome data. If no candidate has sufficient data yet, `get_ranked_keys()` returns
candidates in their pool-defined default order and `ranked[0]` is the governance
operator's preferred first choice.

### Exploration (`draw < epsilon`)

Returns `random.choice(candidates)` — a uniformly random selection from the **full pool
candidate list**, not from the ranked subset.

**Why exploration uses the full candidate list, not the ranked subset:**
A candidate with no historical outcome data is absent from the ranked group. If
exploration sampled only from `ranked`, such candidates would never be explored and
could never accumulate the data needed to enter the ranked group. Uniform sampling
over `candidates` gives every pool candidate an equal exploration probability,
preventing permanent starvation of untried strategies.

### Boundary behavior

`random.random()` returns values in `[0.0, 1.0)`. A draw of exactly `0.05` is NOT less
than epsilon `0.05` — the exploitation path fires. The exploration condition is strictly
`draw < epsilon`.

---

## 8. `fallback_key` Contract

The caller supplies `fallback_key` — a string that is returned unchanged whenever the
service cannot select a pool-based key.

### When `fallback_key` is returned

| Condition | Log level | Rationale |
|---|---|---|
| No active pool for `(trigger_type, dimension)` | None (silent) | Expected state before pools are configured |
| `candidate_keys_json` is `None` | WARNING | Data integrity issue |
| `candidate_keys_json` is `[]` | WARNING | Governance misconfiguration |
| `candidate_keys_json` is malformed JSON | WARNING | Data integrity issue |
| Any exception during pool lookup | WARNING | Unexpected failure |
| Any exception from `get_ranked_keys()` that bypasses `get_ranked_keys()`'s own recovery | WARNING | Extremely unlikely; outer catch |

### Caller-supplied `fallback_key` in `MentorMessageService`

The call site in `mentor_message_service.py` computes `fallback_key` as the existing
mechanical derivation:

```python
_fallback_key = (
    f"{trigger_type}_{trigger_level}".lower().replace(" ", "_")
    if trigger_type and trigger_level else "unknown"
)
```

This ensures that when no pool is configured, the tracked `recommendation_key` is
identical to what the system recorded before `AdaptiveRecommendationService` was
introduced — no regression in recorded data.

---

## 9. Rules

### Deterministic ranking source is mandatory

`select_key()` reads from a SQL table (`AI_ChatBot_RecommendationCandidatePools`) and
calls `RecommendationLearningService.get_ranked_keys()`, which aggregates outcome data
from `AI_ChatBot_InterventionOutcomes`. Both are deterministic: given the same database
state, the same ranked order is returned.

The only non-deterministic element is `random.random()` for the epsilon-greedy draw.
This is intentional and controlled: the draw determines only whether exploitation or
exploration fires, not what the outcome of exploitation is.

**LLM-based recommendation selection is explicitly prohibited.** The selected
`recommendation_key` is recorded by `RecommendationTrackingService` and linked to an
`InterventionOutcome`. The outcome label (`improved` / `not_improved`) then feeds back
into `get_success_rates()`, influencing future rankings. If the selection step used LLM
inference:

1. Rankings would vary across calls for the same database state
2. The outcome attributed to a recommendation would depend on a non-reproducible
   selection process
3. The learning signal would be corrupted — a recommendation's measured success rate
   would reflect both its actual effectiveness and the LLM's selection bias
4. The closed feedback loop would produce unreliable and non-auditable results

### Non-fatal contract is mandatory

`select_key()` must never propagate an exception to the caller. The outer
`try/except Exception` in the implementation is the final catch-all. Any failure that
bypasses all inner recovery paths is logged at WARNING level and resolved by returning
`fallback_key`. The caller's return value and session state are unaffected.

### Changes to default constants require directive and tests first

`_DEFAULT_EPSILON` and `_DEFAULT_MIN_SAMPLE` are business decisions about system-wide
adaptive behavior. Before changing either:

1. Update this directive with the new value and business rationale
2. Update or add tests in `tests/unit/test_adaptive_recommendation_service.py` covering
   the new boundary
3. Only then update the constant in `services/adaptive_recommendation_service.py`

### Changes to the exploration/exploitation algorithm require directive first

The epsilon-greedy algorithm documented in Section 7 is the defined selection contract.
Any change to the algorithm (e.g., adding UCB, switching to softmax, changing what
`random.choice` samples from) must be reflected in this directive before the code
changes. Unit tests must cover the new behavior before deployment.

---

## 10. `RecommendationCandidatePool` — Table Contract

### Purpose

`AI_ChatBot_RecommendationCandidatePools` is a governance-controlled configuration
table. Each row defines, for one trigger context (`trigger_type + dimension`), the
ordered list of candidate `recommendation_key` values that `AdaptiveRecommendationService`
is permitted to select from.

Governance operators write rows into this table to define which recommendation
strategies apply to each trigger context and in what default priority order.

### Active vs inactive behavior

| `is_active` | Behavior |
|---|---|
| `True` | Pool is active; included in lookup query |
| `False` | Pool is soft-disabled; excluded from lookup query; treated as "no pool found" by the service |

Rows are **never deleted**. Disabling a pool by setting `is_active=False` preserves
the pool definition history for audit purposes. To re-enable a pool, set
`is_active=True`; to replace a pool, UPDATE the existing active row — do not insert a
duplicate (the composite UNIQUE constraint prevents it).

### Governance responsibilities

| Responsibility | Owner |
|---|---|
| Define which `(trigger_type, dimension)` contexts should have pools | Governance operator |
| Populate `candidate_keys_json` with valid `recommendation_key` strings | Governance operator |
| Set `epsilon_override` for high-stakes or exploratory contexts | Governance operator |
| Set `min_sample_override` for contexts requiring more or less evidence | Governance operator |
| Disable stale pools by setting `is_active=False` | Governance operator |

The service reads but never writes to this table. All pool management occurs outside
the service layer.

### JSON format expectations

`candidate_keys_json` must contain a valid JSON array. The keys in the array must match
`recommendation_key` values used by `RecommendationTrackingService.record()`. Keys that
do not match any `AI_ChatBot_Recommendations` row will appear in the unranked group
(original order) in `get_ranked_keys()` output — they will never be dropped.

| Validation | Responsibility |
|---|---|
| Valid JSON array | Governance operator at write time |
| Non-empty array | Governance operator — empty array `[]` causes fallback |
| Keys match existing recommendation keys | Governance operator — mismatched keys are handled gracefully |

---

## 11. Call Site Contract in `MentorMessageService`

`select_key()` is called at **both** `RecommendationTrackingService().record()` call
sites in `mentor_message_service.py` — the delivery-failed path and the happy path.

At each site, the pattern is:

```python
with SessionLocal() as rec_session:
    _fallback_key = (
        f"{trigger_type}_{trigger_level}".lower().replace(" ", "_")
        if trigger_type and trigger_level else "unknown"
    )
    recommendation_key = AdaptiveRecommendationService().select_key(
        db           = rec_session,
        trigger_type = trigger_type or "unknown",
        dimension    = trigger_kpi or "general",
        risk_level   = trigger_level,
        fallback_key = _fallback_key,
    )
    RecommendationTrackingService().record(
        ...
        recommendation_key = recommendation_key,
        ...
    )
```

`select_key()` executes first, within the same session as `record()`. Since
`select_key()` is read-only, no state is mutated before `record()` commits.
If `select_key()` returns `fallback_key` (any failure path), `record()` still
executes — the tracked key is the fallback, preserving historical continuity.

---

## 12. Edge Cases

| Condition | Behaviour |
|---|---|
| `trigger_type` is `None` at call site | Pool filter produces `WHERE trigger_type = 'unknown'` (caller passes `trigger_type or "unknown"`); no pool found → `fallback_key` returned |
| `risk_level` is `None` | Forwarded as `None` to `get_ranked_keys()`; treated as "no risk_level filter" — all risk levels included in success rate computation |
| `epsilon_override = 0.0` | Zero exploration — exploitation always fires; `ranked[0]` always returned |
| `epsilon_override = 1.0` | Full exploration — `random.choice(candidates)` always fires |
| `min_sample_override = 0` | All candidates with any eligible outcome are ranked; candidates with no outcomes remain unranked |
| `ranked` is identical to `list(candidates)` (no sufficient-sample keys) | Exploitation returns `candidates[0]` — the governance operator's first-priority candidate |
| Pool has one candidate | Both exploitation and exploration return the same single key |
| `candidate_keys_json = '["key_a"]'` (single entry) | `random.choice(["key_a"])` always returns `"key_a"` — exploration and exploitation are equivalent |
| DB unavailable during pool lookup | Exception caught by outer `try/except`; WARNING logged; `fallback_key` returned |
| `get_ranked_keys()` exception | `get_ranked_keys()` self-recovers to `list(candidates)`; `ranked[0]` returns `candidates[0]` — inner exception is invisible to `select_key()` |

---

## 13. Verification Requirements

Tests live in `tests/unit/test_adaptive_recommendation_service.py`.

| Coverage requirement | Description |
|---|---|
| Pool found returns candidate | Pool exists; result is a key from `_CANDIDATES` |
| Missing pool returns fallback | `first()` returns `None`; `fallback_key` returned without calling learning service |
| Inactive pool treated as missing | `is_active=False` pool excluded by filter; returns `fallback_key` |
| Empty candidate list returns fallback | `candidate_keys_json="[]"`; WARNING logged; `fallback_key` returned |
| Empty candidate list logs WARNING | `logger.warning` called |
| Malformed JSON returns fallback | Unparseable JSON; `fallback_key` returned |
| Malformed JSON logs WARNING | `logger.warning` called |
| `None` candidate JSON returns fallback | `or "[]"` guard; empty list; `fallback_key` returned |
| Exploitation returns `ranked[0]` | `random.random` mocked to `0.99`; `ranked[0]` returned |
| Exploitation does not call `random.choice` | `random.choice` mock assert_not_called |
| Boundary value `draw == epsilon` exploits | `draw=0.05`, `epsilon=0.05`; `0.05 < 0.05` is False → exploitation |
| Exploration calls `random.choice` | `random.random` mocked to `0.00`; `random.choice` called once |
| Exploration uses full candidate list | `random.choice` receives `candidates`, not `ranked` |
| Default epsilon `0.05` triggers exploration at `0.04` | `draw=0.04 < 0.05`; exploration fires |
| Default epsilon `0.05` triggers exploitation at `0.05` | `draw=0.05` is not `< 0.05`; exploitation fires |
| `epsilon_override` raises exploration threshold | `epsilon_override=0.20`; `draw=0.10 < 0.20`; exploration fires |
| Default `min_sample=10` passed | `min_sample_override=None`; `kwargs["min_sample"] == 10` |
| `min_sample_override` passed | `min_sample_override=5`; `kwargs["min_sample"] == 5` |
| `dimension` forwarded | `kwargs["dimension"] == _DIMENSION` |
| `risk_level` forwarded | `kwargs["risk_level"] == _RISK` |
| `candidates` forwarded positionally | `pos_args[1] == _CANDIDATES` |
| Learning service fallback uses `candidates[0]` | `get_ranked_keys` returns `list(candidates)`; `ranked[0] == candidates[0]` |
| DB exception returns `fallback_key` | `db.query.side_effect = Exception`; returns `fallback_key` |
| DB exception does not raise | Same setup; result is `str` |
| DB exception logs WARNING | `logger.warning` called |
| Learning service exception returns `fallback_key` | `get_ranked_keys.side_effect = RuntimeError`; returns `fallback_key` |
| Learning service exception does not raise | Same; result is `str` |
| Return type is always `str` on happy path | `isinstance(result, str)` |
| Return type is always `str` on error | `isinstance(result, str)` |

Run with:

```
pytest tests/unit/test_adaptive_recommendation_service.py -v
```

Current result: **30 passed, 0 failed** (0.49 s — 2026-06-04).

---

## 14. Code Map

| Responsibility | File |
|---|---|
| `AdaptiveRecommendationService.select_key()` | `services/adaptive_recommendation_service.py` |
| `RecommendationCandidatePool` ORM model | `services/models.py` → model #16 |
| Alembic migration | `alembic/versions/0014_add_recommendation_candidate_pools.py` |
| Call site integration | `services/mentor_message_service.py` → `process_trigger()` (both paths) |
| Unit tests | `tests/unit/test_adaptive_recommendation_service.py` |
| Related directive (success rate and ranking) | `directives/recommendation_learning_contract.md` |
| Related directive (recommendation tracking) | `directives/recommendation_learning_contract.md` |
| Related directive (outcome labeling) | `directives/intervention_outcome_contract.md` |

---

## 15. Definition of Done

- [x] `AdaptiveRecommendationService.select_key()` implemented in `services/adaptive_recommendation_service.py`
- [x] `RecommendationCandidatePool` ORM model in `services/models.py`
- [x] Alembic migration `0014_add_recommendation_candidate_pools.py` written
- [x] `select_key()` wired into `mentor_message_service.py` at both call sites
- [x] `fallback_key` is the existing mechanical derivation — no regression in recorded keys when no pool exists
- [x] Unit tests exist and pass (30 tests as of 2026-06-04)
- [x] This directive exists at `directives/adaptive_recommendation_contract.md`
- [x] Epsilon-greedy algorithm documented step-by-step with boundary behavior
- [x] Exploration uses full candidate list — rationale documented
- [x] `fallback_key` contract documented for all failure conditions
- [x] `RecommendationCandidatePool` governance responsibilities documented
- [x] LLM prohibition documented with rationale (feedback loop corruption)
- [x] Constant-change and algorithm-change processes documented
- [ ] Migration 0014 applied to SQL Server (`alembic upgrade head`)
- [ ] `AI_ChatBot_RecommendationCandidatePools` populated with at least one pool definition for testing
- [ ] A junior developer can read this directive and understand exactly how candidate keys are selected, how pools are managed, and why the selection is deterministic
