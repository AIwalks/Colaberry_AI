# Directive: KPI Interpretation Contract

## 1. Purpose

`interpret_kpi()` is a deterministic, rule-based function that converts a raw KPI signal into a human-readable severity assessment for use by student advisors.

It answers one question for each signal: **is this a healthy state that requires no action, or a concerning state that requires advisor attention?**

The function lives in `core/insight/generator.py` and is called by `InsightGenerator.generate_insights()` for every KPI whose confidence exceeds 0.7. Healthy signals (`suppress=True`) are silently dropped before any insight is written. Concerning signals produce titled, advisor-ready text that is presented in the Sentinel dashboard and sent through the mentor messaging pipeline.

This logic is **deterministic**. Given the same `kpi_name` and `value`, `interpret_kpi()` must always return the same result. It does not call any LLM, read from any database, or vary by environment. It is safe to unit-test in full isolation.

---

## 2. Function Signature

```python
def interpret_kpi(kpi_name: str, value: Any, unit: str) -> Dict[str, Any]:
```

### Return shape

| Key | Type | Description |
|---|---|---|
| `severity` | string | `"healthy"`, `"warning"`, `"elevated"`, `"critical"`, or `"unknown"` (fallback only) |
| `suppress` | bool | `True` → healthy; caller must skip insight generation for this KPI |
| `title` | string or None | Advisor-ready one-line summary; `None` for unmapped KPIs (caller uses generic label) |
| `body` | string or None | Advisor-ready narrative text; `None` for unmapped KPIs |
| `recommended_action` | string or None | Specific action for the advisor; `None` for unmapped KPIs |

### suppress=True contract

When `suppress=True`, the `title`, `body`, and `recommended_action` fields are always empty strings. The caller (`InsightGenerator`) must not generate an insight for this KPI. No exception to this rule exists.

When `suppress=False`, all three text fields contain advisor-ready content and must be used as-is without modification by LLM or any downstream rewrite.

---

## 3. Inputs

| Parameter | Type | Notes |
|---|---|---|
| `kpi_name` | string | Signal name from the extraction layer (e.g. `"attendance_percentage"`) |
| `value` | Any | Raw KPI value; coerced to `float` internally for threshold comparison |
| `unit` | string | Unit label (e.g. `"percentage"`, `"days"`); used for display only, not thresholds |

If `value` cannot be coerced to `float` (e.g. `None`, non-numeric string), `interpret_kpi()` falls back to the unmapped-KPI behaviour (`suppress=False`, all text fields `None`). The caller then uses the legacy generic label path.

---

## 4. The 8 KPI Rules

### 4.1 `attendance_percentage`

Measures the fraction of scheduled sessions attended (0.0–1.0).

| Threshold | Severity | suppress | Business rationale |
|---|---|---|---|
| ≥ 0.90 (90%) | healthy | **True** | 90% is the platform attendance benchmark. Students above this threshold are meeting engagement expectations. |
| 0.75–0.89 | warning | False | Below 90% but still attending most sessions. Minor concern — worth noting at the next advisor touchpoint. Not yet predictive of withdrawal. |
| 0.50–0.74 | elevated | False | Historically precedes disengagement. Student is missing more than one in four sessions. Proactive outreach is required this week. |
| < 0.50 | critical | False | Student is absent more often than present. Immediate escalation required. Recovery without intervention is unlikely at this level. |

---

### 4.2 `last_activity_days`

Measures days elapsed since the student last recorded any platform activity.

| Threshold | Severity | suppress | Business rationale |
|---|---|---|---|
| 0–3 days | healthy | **True** | Activity within the past three days indicates normal engagement. No action warranted. |
| 4–7 days | warning | False | A week-long gap may signal the student is falling out of routine. Light monitoring recommended; not yet urgent. |
| 8–13 days | elevated | False | A multi-week gap that frequently precedes measurable disengagement. Proactive outreach is required before the gap widens. |
| ≥ 14 days | critical | False | 14 days is the stale-activity threshold used by `FingerprintGeneratorService`. These signals are aligned intentionally so fingerprinting and interpretation reach the same conclusion. Direct personal contact is required. |

---

### 4.3 `last_login_days`

Measures days elapsed since the student last logged in. Uses the same four-tier threshold scale as `last_activity_days`.

| Threshold | Severity | suppress | Business rationale |
|---|---|---|---|
| 0–3 days | healthy | **True** | Recent login confirms the student is accessing the platform. |
| 4–7 days | warning | False | A week without login is worth noting. Send a check-in if the gap continues. |
| 8–13 days | elevated | False | Access to the platform has likely lapsed. Confirm no access or motivational barrier. |
| ≥ 14 days | critical | False | Aligned with the 14-day stale threshold in `FingerprintGeneratorService`. Login loss at this duration requires personal outreach — automated messaging alone is insufficient. |

**Note:** `last_activity_days` and `last_login_days` use identical thresholds by design. Login and platform activity are distinct signals; a student may log in without engaging. Both signals are evaluated independently.

---

### 4.4 `homeworks_behind`

Counts the number of overdue assignments not yet submitted (integer).

| Threshold | Severity | suppress | Business rationale |
|---|---|---|---|
| 0 | healthy | **True** | No overdue assignments. The student is current. |
| 1–2 | warning | False | Minor academic debt that is still easily recoverable. Worth flagging at the next touchpoint, but not urgent. |
| 3–4 | elevated | False | Academic debt is building. At this level it may affect the student's ability to follow upcoming content. Intervention this week. |
| ≥ 5 | critical | False | Strongly correlated with program withdrawal if not addressed immediately. Escalation to an academic advisor is required. |

---

### 4.5 `avg_hw_score`

Average assignment score on a 0–100 scale.

| Threshold | Severity | suppress | Business rationale |
|---|---|---|---|
| ≥ 85 | healthy | **True** | 85 is the platform benchmark for acceptable mastery. Students at or above this threshold are demonstrating sufficient understanding. |
| 70–84 | warning | False | Passing but below the benchmark. Some content gaps are likely present. Worth reviewing at the next touchpoint. |
| 55–69 | elevated | False | The student is struggling to demonstrate mastery of core content. A targeted academic support session is needed. |
| < 55 | critical | False | Below the platform passing threshold. The student needs immediate academic intervention — do not wait for a scheduled touchpoint. |

---

### 4.6 `submission_rate` / `assignment_submission_rate`

Fraction of assigned work submitted (0.0–1.0). Both KPI names route to the same interpreter. `assignment_submission_rate` is an alias — the two names are treated identically.

| Threshold | Severity | suppress | Business rationale |
|---|---|---|---|
| ≥ 0.90 (90%) | healthy | **True** | Submitting 90% or more of assigned work is the expected standard. |
| 0.75–0.89 | warning | False | Some assignments are being skipped. Worth confirming there are no barriers to specific assignment types. |
| 0.50–0.74 | elevated | False | A significant portion of assigned work is missing. Contact this week to understand whether the cause is workload, comprehension, or access. |
| < 0.50 | critical | False | The student is not completing most assigned work — a strong predictor of withdrawal. Urgent outreach and a concrete re-engagement plan are required. |

**Threshold alignment note:** `submission_rate` and `attendance_percentage` share the same 90/75/50 threshold boundaries intentionally. This presents advisors with a consistent framework — the same mental model applies to both attendance and submission behaviour.

---

### 4.7 `trigger_completion_rate`

Fraction of advisor outreach (trigger) attempts that were completed (0.0–1.0).

| Threshold | Severity | suppress | Business rationale |
|---|---|---|---|
| ≥ 0.60 (60%) | healthy | **True** | Responding to 60% or more of outreach is acceptable for advisor-initiated contact. The healthy bar is lower here than for submission/attendance because outreach completion is influenced by channel effectiveness, not solely student behaviour. |
| 0.40–0.59 | warning | False | Inconsistent responsiveness. Some messages are not getting through. Review delivery logs and consider timing or channel adjustments. |
| 0.25–0.39 | elevated | False | The current outreach approach is not reliably reaching this student. A change of channel or timing is warranted. |
| < 0.25 | critical | False | Standard outreach has effectively failed. Escalate to direct personal contact (phone or video). Document all attempts. |

---

### 4.8 `intervention_completion_rate`

Fraction of formal intervention attempts that were completed (0.0–1.0). Uses the same four-tier structure as `trigger_completion_rate` but with a **raised healthy threshold of 0.70**.

| Threshold | Severity | suppress | Business rationale |
|---|---|---|---|
| ≥ 0.70 (70%) | healthy | **True** | Interventions are higher-stakes than general outreach. A 70% completion rate is required before the intervention programme is considered effective for this student. |
| 0.50–0.69 | warning | False | Intervention completion is below the expected level. Review recent intervention delivery logs. |
| 0.25–0.49 | elevated | False | Only a quarter to half of interventions are completing. The current approach is not working. Change channel or method. |
| < 0.25 | critical | False | Formal intervention has failed. Escalate to direct personal contact and document all attempts and outcomes. |

**Rationale for higher healthy threshold:** Interventions are designed responses to identified risk. If they are not completing, the risk is not being addressed. The gap between the `trigger_completion_rate` healthy threshold (0.60) and the `intervention_completion_rate` healthy threshold (0.70) is intentional — advisors should be held to a higher standard of follow-through for formal interventions.

---

## 5. Fallback Behaviour for Unknown KPIs

Any `kpi_name` not explicitly listed in Section 4 falls through to `_fallback_kpi()`:

- `suppress=False` — the signal is preserved; the caller generates an insight
- `title=None`, `body=None`, `recommended_action=None` — signals the caller to use the legacy generic label path in `InsightGenerator` rather than the deterministic text
- `severity="unknown"` — no severity classification applied

This fallback preserves backwards compatibility. Newly discovered KPI names that are not yet mapped will still surface in insights with a generic label rather than being silently dropped.

---

## 6. Rules

### Determinism is mandatory

`interpret_kpi()` must never call any LLM, external API, database, or file system. Given the same `kpi_name` and `value`, it must always return the same result. This property enables:
- Reliable unit testing in full isolation
- Predictable advisor experience
- Safe replay and debugging

Any proposal to replace threshold logic with LLM judgment is rejected by this directive.

### Threshold changes require this directive and tests to be updated first

The thresholds in Section 4 are **not free variables**. They represent business decisions about student risk. Before changing any threshold value:

1. Update this directive with the new threshold and the business rationale for the change
2. Update or add unit tests in `tests/unit/test_interpret_kpi.py` to cover the new boundary values
3. Only then update the code in `core/insight/generator.py`

The definition of done for a threshold change is: directive updated → tests updated and passing → code updated.

### Adding a new KPI mapping

When a new KPI name is identified that warrants deterministic interpretation:
1. Add a section to this directive (following the table format in Section 4) with thresholds and business rationale
2. Write unit tests covering all severity bands and boundary values (fence-posts)
3. Implement the interpreter function in `core/insight/generator.py`
4. Wire the new name into `interpret_kpi()` with an explicit `if kpi_name == "..."` branch

Do not add a new KPI mapping to code without a corresponding directive section.

### suppress=True signals carry no text

When `suppress=True`, the caller must not generate an insight. The empty strings in `title`, `body`, and `recommended_action` are intentional sentinels. Callers must check `suppress` before accessing text fields. Tests must verify the suppression contract for every healthy boundary.

---

## 7. Edge Cases

| Condition | Behaviour |
|---|---|
| `value` is `None` | `float(None)` raises `TypeError`; falls back to `_fallback_kpi()` — `suppress=False`, all text `None` |
| `value` is a non-numeric string (e.g. `"N/A"`) | `float("N/A")` raises `ValueError`; same fallback as `None` |
| `value` is exactly at a threshold boundary (e.g. `attendance=0.90`) | Upper band wins — `0.90` is healthy (`≥ 0.90`) |
| `kpi_name` not in the 8 mapped names | `_fallback_kpi()` — legacy generic path preserved |
| `submission_rate` and `assignment_submission_rate` both arrive for the same student | Both route to the same interpreter; both produce an insight independently; deduplication is the responsibility of the upstream caller, not `interpret_kpi()` |
| `last_activity_days` and `last_login_days` both arrive for the same student | Both are evaluated independently; both may produce insights at the same severity level |

---

## 8. Verification Requirements

Tests live in `tests/unit/test_interpret_kpi.py`.

The test suite must cover:

| Coverage requirement | Description |
|---|---|
| All 8 KPI names | Each mapped KPI name must have at least one test |
| All 4 severity bands per KPI | healthy, warning, elevated, critical each tested with a representative value |
| Boundary values (fence-posts) | The exact threshold value and the value one unit above/below it must each be tested |
| suppress=True contract | Every healthy result must assert `suppress is True` and that text fields are empty strings |
| Non-numeric fallback | `None` and a non-numeric string must each produce the fallback result |
| Alias mapping | `submission_rate` and `assignment_submission_rate` must both produce identical results for the same value |
| Integration smoke-test | `InsightGenerator.generate_insights()` called with a healthy KPI must produce zero insights; called with a critical KPI must produce one insight |

Run with:

```
pytest tests/unit/test_interpret_kpi.py -v
```

Current result: **127 passed, 0 failed** (as of 2026-06-03).

---

## 9. Code Map

| Responsibility | File |
|---|---|
| `interpret_kpi()` entry point | `core/insight/generator.py` |
| `_interp_attendance()` | `core/insight/generator.py` |
| `_interp_days_inactive()` (shared by last_activity_days and last_login_days) | `core/insight/generator.py` |
| `_interp_homeworks_behind()` | `core/insight/generator.py` |
| `_interp_avg_hw_score()` | `core/insight/generator.py` |
| `_interp_submission_rate()` | `core/insight/generator.py` |
| `_interp_completion_rate()` (shared by trigger_ and intervention_completion_rate) | `core/insight/generator.py` |
| `_fallback_kpi()` | `core/insight/generator.py` |
| Caller (suppression check and text use) | `core/insight/generator.py` → `InsightGenerator.generate_insights()` |
| Unit tests | `tests/unit/test_interpret_kpi.py` |
| Related directive (fingerprint thresholds) | `directives/behavior_fingerprint_contract.md` |
| Related directive (insight generation) | `directives/insight_contract.md` |

---

## 10. Definition of Done

- [x] `interpret_kpi()` implemented in `core/insight/generator.py`
- [x] All 8 KPI names mapped with deterministic threshold logic
- [x] Unit tests exist and pass for all 8 KPI interpreters, all severity bands, all boundary values, and the fallback path (`tests/unit/test_interpret_kpi.py` — 127 passed as of 2026-06-03)
- [x] This directive exists at `directives/kpi_interpretation_contract.md`
- [x] Thresholds documented with business rationale (Section 4)
- [x] suppress=True contract documented (Section 2 and Section 6)
- [x] Threshold-change process documented (Section 6)
- [x] A junior developer can read this directive and know exactly what values trigger each severity level and what action the advisor is expected to take
