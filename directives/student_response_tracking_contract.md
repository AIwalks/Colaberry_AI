# Directive: Student Response Tracking Contract

**Last updated:** 2026-05-04
**Covers:** `AI_ChatBot_StudentResponses` (planned), `services/mentor_message_service.py`, `services/engagement_tracker_service.py`
**Classification:** Architecture-critical — schema and matching logic changes require explicit owner approval

---

## 1. Purpose

This directive defines how the Colaberry AI system must link **inbound student messages**
(replies) back to the **outbound trigger records** that prompted them.

When a student replies to a system-generated nudge, reminder, or coaching message, the
system needs to know:

- *Which trigger fired?* (`TriggeredUser.CBM_ID`)
- *Was the reply received on the same channel the trigger was delivered on?*
- *How confident is the association?* (deterministic match vs. heuristic guess)

This linkage enables:

- Accurate delivery outcome measurement (beyond `DeliverySucceeded` — did the student
  actually respond?)
- Re-engagement logic (do not resend a trigger the student already replied to)
- Attribution data for future ML-based response prediction
- Student journey visibility: trigger → delivery → response → outcome

Response tracking is a **measurement system**. It must not alter student-facing behavior,
delivery logic, or trigger evaluation. It runs after the fact, appending association records
to a dedicated table.

---

## 2. Why Direct Linking at Ingestion Time Is Unsafe

When an inbound message arrives at `POST /ai/mentor/message`, the system knows:

- `student_id` (from the request body)
- `channel` (from the request body)
- `thread_id` (optional; present only when the channel supports threading)
- The current timestamp

The system does **not** know, at ingestion time, which specific `TriggeredUser` row the
student is replying to. A student may have received multiple triggers across multiple
channels within a short window. There is no guaranteed signal in an inbound SMS that
identifies the trigger that prompted it.

Attempting to resolve this at ingestion time requires guessing. Guessing produces incorrect
associations. An incorrect association is worse than no association:

- A false "responded" signal on the wrong trigger row suppresses future legitimate triggers
  for that student
- Downstream analytics count a non-response as a response
- The error propagates silently into any model trained on this data

**The system must never write a `cbm_id` or `trigger_id` value into any inbound record
without a confidence score and a declared match method. Hardcoding `None` is correct and
safe. Guessing is not.**

The current implementation (`CBM_ID=None` and `trigger_id=None` hardcoded in
`mentor_message_service.py`) is the correct safe default. The goal of this system is to
replace those `None` values with verified associations, not to guess associations faster.

---

## 3. Deterministic vs. Non-Deterministic Matching

| Match Method | Deterministic? | Confidence | Description |
|---|---|---|---|
| `thread_id` | **Yes** | 1.0 | Channel provides a thread identifier that was echoed in the outbound message; the inbound message carries the same identifier. Unambiguous. Only available on channels that support threading (WhatsApp, web chat). Not available on SMS. |
| `manual` | **Yes** | 1.0 | A human operator or administrator explicitly assigns the association. Used for corrections and edge-case resolution. |
| `time_proximity` | **No** | 0.0–0.7 | The most recent `TriggeredUser` row for the student whose `CompletedDate` falls within a configurable window before the inbound message timestamp. Confidence decays with distance from the window midpoint and drops further when multiple qualifying triggers exist in the same window. |

**Only deterministic matches may be acted on by automated business logic** (e.g.,
suppressing a re-trigger). Non-deterministic matches may be stored for analytical purposes
but must not affect delivery decisions without explicit operator review.

---

## 4. Approved Architecture

### 4.1 Additive Mapping Table — `AI_ChatBot_StudentResponses`

All response-to-trigger associations are stored in a dedicated table. Existing tables are
**never mutated** to record this association.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | Integer PK autoincrement | No | Surrogate key |
| `cbm_id` | Integer | No | References `AI_ChatBot_TriggeredUsers.CBM_ID` — the outbound trigger being replied to |
| `engagement_event_id` | Integer | No | References `AI_ChatBot_EngagementEvents.id` — the inbound event |
| `user_id` | Integer | No | Denormalized from the inbound event; enables fast per-student queries without joins |
| `response_channel` | String(50) | No | The channel on which the reply arrived (e.g. `"sms"`, `"whatsapp"`, `"web"`) |
| `match_method` | String(30) | No | One of: `"thread_id"`, `"time_proximity"`, `"manual"` |
| `confidence` | Float | No | 0.0–1.0; see Section 6 |
| `matched_at` | DateTime UTC | No | When the association was created, not when the inbound message arrived |

No foreign key constraints are enforced at the database level in the initial implementation
(SQL Server FK constraints require careful migration ordering). The columns are
semantically FK-referenced but not DDL-constrained. This is consistent with the existing
pattern in this codebase.

### 4.2 No Mutation of Existing Tables

The following tables must **not** be altered to record response associations:

| Table | Reason |
|---|---|
| `AI_ChatBot_TriggeredUsers` | Trigger records represent outbound events; they must not carry inbound data fields |
| `AI_ChatBot_AuditLog` | Audit entries are append-only event records; `CBM_ID` remains `None` on inbound entries until a verified association is made |
| `AI_ChatBot_EngagementEvents` | `trigger_id` remains `None` on inbound entries until a verified association is made |

Associations are recorded by **adding a row to `AI_ChatBot_StudentResponses`**, not by
updating an existing row in any of the three tables above.

### 4.3 Prerequisite — Store `thread_id` on `EngagementEvent`

Before deterministic thread-based matching is possible, `thread_id` must be persisted on
the `EngagementEvent` row created when an inbound message is received.

`thread_id` already exists on the `MentorMessageRequest` schema but is not currently
stored. The approved implementation order is:

1. Add `thread_id` (nullable String) column to `AI_ChatBot_EngagementEvents` via Alembic
   migration.
2. Pass `thread_id` from `MentorMessageService.handle()` through to
   `EngagementTrackerService.log_event()`.
3. Store the value on the `EngagementEvent` row when present; leave `None` when absent.

This step is non-breaking, additive, and does not require the `AI_ChatBot_StudentResponses`
table to exist yet.

---

## 5. Matching Methods (Implementation)

### 5.1 `thread_id` (Deterministic)

**When it applies:** The inbound `MentorMessageRequest` contains a non-null `thread_id`
AND an outbound `DeliveryLog` record exists with the same `thread_id` for this student.

**Resolution:**
1. Look up the `DeliveryLog` row where `thread_id` matches and `user_id` matches.
2. Retrieve `cbm_id` from that delivery log row.
3. Create a `StudentResponse` row with `match_method="thread_id"`, `confidence=1.0`.

**Failure mode:** No matching `DeliveryLog` found with that `thread_id`. Do not create
a `StudentResponse` row. Log a warning. Do not fall back to time-proximity automatically.

### 5.2 `time_proximity` (Heuristic)

**When it applies:** No `thread_id` is available, and an operator-configured time window
is enabled for the channel.

**Resolution:**
1. Query `AI_ChatBot_TriggeredUsers` for the student's most recent completed trigger(s)
   within the configured window (e.g. 72 hours) before the inbound timestamp.
2. If exactly one trigger qualifies: create a `StudentResponse` row with
   `match_method="time_proximity"` and a confidence derived from the time distance
   (closer = higher; multiple triggers in window = lower).
3. If zero triggers qualify: no association. Do not create a row.
4. If multiple triggers qualify within the window: calculate individual confidence for
   each. Only create a row if one trigger has confidence ≥ the configured threshold and
   all others are below it. If two or more are at or above threshold, create no row —
   the ambiguity is unresolvable without additional signal.

**Confidence formula (reference, not normative — may be refined before implementation):**

```
hours_elapsed = (inbound_timestamp - trigger.CompletedDate).total_seconds() / 3600
raw_confidence = max(0.0, 1.0 - (hours_elapsed / window_hours))
final_confidence = raw_confidence * (1.0 / qualifying_trigger_count)
```

The time-proximity confidence ceiling is 0.7. A time-proximity match must never carry
confidence > 0.7 regardless of elapsed time. Values above 0.7 imply deterministic signal.

### 5.3 `manual`

An administrator or operator directly creates a `StudentResponse` row with
`match_method="manual"` and `confidence=1.0` via an internal tool or direct database
insert. No service code handles this path in the initial implementation.

---

## 6. Confidence Scoring Requirements

Every `StudentResponse` row **must** carry a confidence score. There is no valid
`StudentResponse` row with a null or missing confidence.

| Confidence | Meaning |
|---|---|
| `1.0` | Deterministic — `thread_id` or `manual`. Safe for automated business logic. |
| `0.5–0.7` | Heuristic — time-proximity with moderate certainty. Analytical use only. |
| `< 0.5` | Heuristic — ambiguous. Stored for ML training data; must not influence delivery decisions. |
| `0.0` | Not used. A confidence of zero means the association should not be recorded. |

Any system component that reads `AI_ChatBot_StudentResponses` for a business decision
(e.g., should we resend this trigger?) must filter to `confidence = 1.0` unless the
operator has explicitly configured a lower threshold with documented justification.

---

## 7. Data Integrity Rules

### Append-only

`AI_ChatBot_StudentResponses` is an append-only log. Rows are never updated in place.

If an association is determined to be wrong:
1. Delete the incorrect row.
2. Insert a corrected row with `match_method="manual"` and `confidence=1.0`.
3. Log both the deletion and the insertion in `AI_ChatBot_AuditLog`.

### Reversibility

Because response tracking rows are additive and separate from the tables they reference,
they can be rolled back without affecting trigger records, engagement events, or audit logs.
Dropping the `AI_ChatBot_StudentResponses` table or deleting all its rows has zero effect
on any existing record in any other table.

### No cascading deletes

If a `TriggeredUser` row or `EngagementEvent` row is deleted (which should be rare and
approval-gated), the corresponding `StudentResponse` rows become orphaned references.
This is acceptable: orphaned response rows are harmless and detectable via a query.
They must not be deleted automatically by a cascade constraint.

### No upsert / merge semantics

No code path may use `INSERT OR REPLACE`, `MERGE`, or equivalent. All writes are plain
inserts. Detecting a duplicate before inserting is the caller's responsibility.

### No historical backfill without a defined strategy

Historical inbound records (`EngagementEvents` with `trigger_id=None`) must not be
retroactively matched against `TriggeredUser` rows unless:

1. A matching strategy (method + confidence formula) has been explicitly defined and
   approved in this directive.
2. Every row produced by the backfill carries `match_method` and a calculated `confidence`
   score — never a hardcoded `1.0` applied uniformly to heuristic matches.
3. The backfill run is logged with a start timestamp, end timestamp, row count, and
   method applied, so it can be identified and reversed if the strategy is later found
   to be incorrect.

Running a backfill without a defined strategy produces untraceable, unversioned
associations that corrupt both operational decisions and ML training data. If no approved
strategy exists yet, the correct action is to leave historical `trigger_id=None` values
in place.

---

## 8. Idempotency Requirements

### One association per inbound event

`AI_ChatBot_StudentResponses` must contain at most one row per `engagement_event_id`
under normal operation. An inbound event represents a single student reply; creating
multiple association rows for the same event produces duplicate signals in analytics and
delivery suppression logic.

Before inserting a new `StudentResponse` row, the caller must check whether a row
already exists for the given `engagement_event_id`:

- If no row exists: insert normally.
- If a row exists with the same `cbm_id` and `match_method`: the insert is a duplicate.
  Log at DEBUG level and take no further action. Do not raise an exception.
- If a row exists with a different `cbm_id` or `match_method`: this is a conflict, not
  a duplicate. Do not overwrite silently. Log at WARNING level, record in
  `AI_ChatBot_AuditLog`, and require a `manual` override to resolve.

### Explicit override path

A `manual` association may replace an existing row for the same `engagement_event_id`
when an operator determines the original association was wrong. The override process is:

1. Delete the existing row (logged in `AI_ChatBot_AuditLog`).
2. Insert the corrected row with `match_method="manual"` and `confidence=1.0`.

No code path may silently overwrite an existing row. Overwrite-by-update is never
permitted — only delete-then-insert with both steps logged.

### Test requirement

Two tests must cover idempotency:

| # | Scenario | Expected |
|---|---|---|
| I-1 | Matcher runs twice for the same `engagement_event_id` and same `cbm_id` | Second run inserts no row; no exception raised |
| I-2 | Conflict: existing row has different `cbm_id` | WARNING logged; no row inserted; no exception raised |

---

## 9. What MUST NOT Happen

The following behaviors are explicitly prohibited and must be caught in code review:

| Prohibited | Reason |
|---|---|
| Writing `cbm_id` to `AuditLog` or `trigger_id` to `EngagementEvents` without a verified association | Creates false linkage at ingestion time |
| Creating a `StudentResponse` row with a guessed `cbm_id` and no `confidence` field | Untracked guesses are indistinguishable from verified matches |
| Auto-linking the most recent trigger to every inbound message unconditionally | This is guessing with extra steps; fails when a student has multiple recent triggers |
| Using `time_proximity` matching when `confidence < configured_threshold` | Ambiguous associations must not be stored |
| Using a heuristic match to suppress or alter delivery decisions | Only `confidence=1.0` matches are safe for automated business logic |
| Modifying `TriggeredUser.Completed`, `TriggeredUser.CompletedDate`, or `TriggeredUser.DeliverySucceeded` as part of response tracking | Those fields belong to the delivery pipeline, not the response tracking pipeline |
| Deleting `StudentResponse` rows without an audit log entry | All deletions must be visible in `AI_ChatBot_AuditLog` |
| Running matching logic in the inbound message request/response cycle in any form | Matching **must** run in a background process or scheduled job. It is not permitted to defer matching to an `asyncio` task, a thread, or any construct that shares the request lifetime. The route handler must return before any matcher executes. Violation of this rule adds latency to student-facing responses and creates coupling between delivery reliability and matching correctness. |

---

## 10. ML Attribution Support

The `AI_ChatBot_StudentResponses` table is the primary training-data source for any future
model that predicts student response likelihood given trigger type, channel, time of day,
trigger level, or student lifecycle stage.

To preserve the integrity of that training data:

**Every row must carry `match_method` and `confidence`.** A model trained on rows without
provenance cannot distinguish ground truth from noise. `match_method` and `confidence`
become features in attribution modeling — they are not metadata; they are data.

**Low-confidence rows must be labelled, not excluded.** Remove low-confidence rows from the
training set only when training a precision model. For coverage models, low-confidence rows
with their confidence score as a feature produce more robust predictions than a dataset
artificially filtered to only high-confidence events.

**The time window used for `time_proximity` matching must be versioned.** If the window
changes (e.g. from 48 hours to 72 hours), rows created under the old window must retain the
confidence score they were assigned at creation time. Do not retroactively recalculate
confidence when configuration changes.

**`matched_at` is not the event time.** `matched_at` records when the association was
created, not when the student replied. `EngagementEvent.created_at` is the event time.
Any ML pipeline must join on `engagement_event_id` to retrieve the true event timestamp.

---

## 11. Required Test Coverage

All tests must live under `tests/unit/` or `tests/e2e/`. No test may touch a live database
or send a real message.

| # | Test | Expected |
|---|---|---|
| 1 | `thread_id` present on inbound request → stored on `EngagementEvent` | Field is non-null after `handle()` |
| 2 | `thread_id` absent on inbound request → `None` on `EngagementEvent` | Field remains `None` |
| 3 | Thread-based matcher finds matching `DeliveryLog` → `StudentResponse` created with `confidence=1.0`, `match_method="thread_id"` | Row exists with correct fields |
| 4 | Thread-based matcher finds no matching `DeliveryLog` → no `StudentResponse` created | Row does not exist; no exception raised |
| 5 | Time-proximity matcher: one trigger in window → `StudentResponse` created with `confidence ≤ 0.7`, `match_method="time_proximity"` | Row exists with correct method and bounded confidence |
| 6 | Time-proximity matcher: two triggers in window both above threshold → no row created | Ambiguity resolved by creating nothing |
| 7 | Time-proximity matcher: no trigger in window → no row created | No exception; no row |
| 8 | `StudentResponse` row with `confidence=0.8` not used in delivery suppression decision | Delivery logic reads only `confidence=1.0` rows |
| 9 | Matching does not run in the request/response cycle | `handle()` returns before any matcher is invoked; matcher runs in a background process or scheduled job only |
| I-1 | Matcher runs twice for the same `engagement_event_id` and same `cbm_id` | Second run inserts no row; no exception raised |
| I-2 | Conflict: existing row has different `cbm_id` for the same `engagement_event_id` | WARNING logged; no row inserted; no exception raised |

**Tooling:** pytest with FastAPI TestClient. SQLite or in-memory session for write tests.
All matchers must be importable and testable without a network connection.

---

## 12. Definition of Done

- [ ] This directive exists at `directives/student_response_tracking_contract.md` and is clear to a junior developer
- [ ] `thread_id` column added to `AI_ChatBot_EngagementEvents` via Alembic migration
- [ ] `thread_id` persisted from `MentorMessageRequest` through `handle()` → `log_event()`
- [ ] `AI_ChatBot_StudentResponses` ORM model and Alembic migration created
- [ ] Thread-based matcher implemented and unit-tested (tests 3–4 above)
- [ ] Time-proximity matcher implemented and unit-tested (tests 5–7 above)
- [ ] Delivery suppression reads only `confidence=1.0` associations (test 8 above)
- [ ] Matching runs in a background process or scheduled job — never in the request/response cycle (test 9 above)
- [ ] Duplicate insert for same `engagement_event_id` is safely ignored (test I-1 above)
- [ ] Conflict for same `engagement_event_id` with different `cbm_id` logs WARNING and inserts nothing (test I-2 above)
- [ ] No historical backfill run without a defined strategy, logged start/end, and per-row confidence
- [ ] All matching creates entries in `AI_ChatBot_AuditLog` for traceability
- [ ] No secrets introduced in the repository
- [ ] `MSSQL_CONFIGURED` guard respected — no matching logic runs against production without explicit opt-in
