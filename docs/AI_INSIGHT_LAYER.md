# AI Insight Layer
**Colaberry Sentinel OS | Internal Engineering Document**
**Status: MVP — Not yet wired into production routes**
**Last updated: 2026-05-11**

---

## Purpose

The AI insight layer exists to make the system honest about what it claims to be.

The existing orchestration pipeline — threshold evaluation, trigger dispatch, message delivery — works correctly and deterministically. What it cannot do is reason about what a student's data pattern *means*, generate a natural-language explanation of that pattern, or produce a confidence-weighted recommendation that a mentor can act on. Prior to this layer, the system returned pre-written template strings from a database column and labelled them "AI-generated." That claim was false.

The AI insight layer introduces a genuine inference step: given a student's KPI signals and behavioral fingerprint data, the system calls the Anthropic Claude API, receives a structured response, validates that response against a documented contract, and returns an explainable, confidence-scored insight.

**Why it was introduced separately from the existing orchestration pipeline:**

The existing pipeline is synchronous, deterministic, and tested. Inserting a probabilistic external API call into that pipeline would couple its reliability to network availability, API rate limits, and model response latency. A student trigger that fires at 2 AM should not fail to log an engagement event because the Claude API returned a 429. Separating the AI layer means: the orchestration pipeline continues to operate regardless of AI availability. The AI insight layer is an enrichment, not a dependency.

**How it upgrades the MVP architecture:**

The MVP previously had three honest capabilities: threshold-based trigger evaluation, message delivery via Twilio, and append-only audit logging. It now has a fourth: genuine AI-generated reasoning over student data, with a validated response contract, a documented fallback model, and deterministic unit test coverage of every failure path. The system can now honestly claim intelligence on the data it observes.

---

## Architectural Isolation Strategy

### The service is isolated by design

`services/ai_insight_service.py` imports nothing from the existing service layer. It has no reference to `TriggerProcessingService`, `MentorMessageService`, `OutboundDeliveryService`, or any ORM model. Its only dependencies are the Python standard library (`json`, `logging`, `os`) and the `anthropic` SDK.

This isolation is intentional and load-bearing. It means:

- The service can be called from any context — a new API route, a background job, a test harness — without pulling in the database session lifecycle or the trigger pipeline state.
- A failure in the AI layer cannot propagate into the orchestration pipeline. There is no shared exception surface.
- The service can be removed, replaced, or upgraded without touching any other file.

### Why no ORM or database coupling exists

The service accepts a plain Python `dict` and returns a plain Python `dict`. It does not receive a `Session`, does not query any table, and does not write any row. This is a deliberate choice, not an oversight.

If the service held a database session, every test would require a database fixture. Every deployment would require the session lifecycle to be correctly threaded through. Every call would carry the overhead of connection pool management even when the result is a simple fallback.

The caller — whether `InsightService` or a future route — is responsible for loading data from the database and for persisting the result. The AI layer is a pure transformation: data in, structured insight out. Transformation functions should not own I/O.

### Why additive-only integration matters

Sentinel OS is an intelligence overlay on a production SQL Server system. The production tables (`AI_ChatBot_TriggerData`, `AI_ChatBot_TriggerRules`) are read-only by contract. The overlay system adds tables; it does not modify production schema.

The AI insight layer applies the same principle to service architecture. It adds a capability without modifying any existing service. `trigger_processing_service.py`, `mentor_message_service.py`, and `trigger_worker.py` are unchanged. If the AI layer is removed entirely tomorrow, the system returns to its pre-AI state with zero code changes to the pipeline.

Additive integration matters because it preserves the invariant that working, tested code cannot be broken by a new feature. In a system where one service owns student outreach, breaking that service has real consequences for real students. The only safe way to add intelligence to such a system is to add it alongside, not inside.

### How this follows the "Freeze the Core" principle

The Sentinel OS design philosophy treats the existing production system as immutable infrastructure. Sentinel OS observes, enriches, and acts — but never rewrites what is already working.

The AI insight layer is the first application of this principle to the service layer itself. The existing services are the core. The AI layer wraps around them, reading their outputs and enriching the insight plane, without touching their internals. This is the same relationship Sentinel OS has with SQL Server, applied one level up.

---

## Response Contract

Every call to `generate_ai_insight()` — whether it reaches the Claude API or triggers a fallback — returns a dict with exactly this shape:

```python
{
    "summary":            str,    # one to two sentence plain-English state assessment
    "risk_level":         str,    # one of: "low" | "medium" | "high" | "critical" | "unknown"
    "confidence":         float,  # 0.0 to 1.0 — strength of data support for risk_level
    "recommended_action": str,    # specific, actionable guidance for a mentor or advisor
    "explainability":     list[str]  # 2–4 reasons drawn from the input data
}
```

`"unknown"` is a valid `risk_level` value — it is the sentinel for the degraded-state (fallback) response. See the Fallback Safety Model section for details.

### Why strict validation exists

The Claude API returns natural language that is then parsed as JSON. Natural language models are not compilers. They may omit a field, return a `risk_level` value outside the defined set, or return `explainability` as a string rather than a list. These are not hypothetical failures — they are observed failure modes in production AI systems.

The `_validate()` function enforces the contract before the response reaches any caller. It checks for required fields, validates `risk_level` against the allowed set, coerces `confidence` to `float`, and verifies that `explainability` is a list. If any check fails, the response is rejected and the fallback is returned. The caller never receives a partially-structured response.

### Why deterministic structure matters

A caller that checks `result["risk_level"] == "high"` must be able to trust that `risk_level` is always present, always a string, and always one of a known set of values. If that trust is conditional — present sometimes, absent when the API is slow — the caller must add defensive code at every call site. Defensive code that compensates for an inconsistent interface is a maintenance tax that grows with every new caller.

The response contract eliminates that tax. The caller can pattern-match on `risk_level`, render `explainability` as a list, and display `confidence` as a percentage without any `isinstance` checks or `try/except` wrapping. The service owns the defensive logic; the caller owns the business logic.

### How downstream systems can rely on this contract

The contract has one machine-detectable degraded-state signal: `confidence == 0.0` combined with `risk_level == "unknown"`. Any downstream system — a route, a frontend component, a future governance workflow — can detect that the AI layer was unavailable and route accordingly. This signal is intentional: a confidence score of 0.0 is not a valid AI output (a model that is 0% confident in its assessment has no useful output to report). It is reserved exclusively for the fallback.

---

## Fallback Safety Model

`generate_ai_insight()` never raises an exception. Under every failure condition, it returns the fallback dict and logs the failure at the appropriate level. The caller always receives a valid response in the documented contract shape.

### Fallback paths

**1. `ANTHROPIC_API_KEY` not set**
Detected at entry before any network call is attempted. Logs a `WARNING`. Returns fallback immediately. This is the expected state in development environments where the key has not been configured.

**2. `anthropic` SDK not installed**
The import of `anthropic` is deferred to the moment of the API call, not at module load time. If the package is absent, `ImportError` is caught, an `ERROR` is logged with the install instruction, and the fallback is returned. The application server continues to boot and operate normally.

**3. Claude returns malformed or non-JSON response**
`json.JSONDecodeError` is caught explicitly. The raw response text is not propagated. Logs `ERROR` with the parse failure detail. Returns fallback.

**4. API or network failure**
Any exception not matched by a more specific handler — connection timeout, HTTP 5xx, rate limit exhaustion, SSL error — is caught by the broad `Exception` handler. Logs `ERROR` with the exception message. Returns fallback. This catch is intentional: the goal is to contain all AI-layer failures within the service boundary.

**5. Validation failure**
If the Claude response parses as valid JSON but fails structural validation (missing required fields, `risk_level` outside the allowed set, `explainability` not a list), `ValueError` is raised by `_validate()`, caught by the caller, logged as `ERROR`, and converted to fallback. A structurally invalid response is treated the same as no response.

### Why `confidence = 0.0` and `risk_level = "unknown"` are machine-detectable signals

A confidence score of exactly `0.0` cannot be a legitimate AI inference result. No model that has analyzed data and reached a conclusion would assign zero confidence to that conclusion — it would simply not return a result. Reserving `0.0` for the fallback state means any downstream consumer can reliably distinguish "AI returned a low-confidence result" (e.g., `0.31`) from "AI was not available" (`0.0`) without parsing error messages or checking for `None`.

`"unknown"` serves the same role for `risk_level`. The valid inference values are `low`, `medium`, `high`, and `critical`. `"unknown"` is outside this set by design. A routing rule, a dashboard filter, or a governance workflow can use `risk_level == "unknown"` as a trigger for human review without any additional state tracking.

---

## Testing Philosophy

### Why tests are deterministic

Unit tests that call the real Claude API are not unit tests — they are integration tests with network dependencies, token costs, and model-version sensitivity. A unit test must produce the same result on the same code regardless of network state, API availability, or model behavior. If a test fails on a Tuesday because the Claude API returned a slightly different JSON structure, the failure is not informative about the code under test.

The AI insight service tests are deterministic because every external dependency is replaced with a controlled substitute before the test runs.

### Why real API calls are prohibited in unit tests

Three concrete reasons:

1. **CI portability** — the CI environment does not have `ANTHROPIC_API_KEY` configured by default. Tests that require it will fail in CI, blocking every merge.
2. **Cost and rate limits** — at scale, test runs happen dozens of times per day. API token consumption in tests competes with production usage.
3. **Contract stability** — the test proves that *given this input to the service, the service returns this output*. The Claude model is not the subject of the test; the service's handling of Claude's output is. Mocking `_call_claude` isolates the subject correctly.

### How mocking is used

The primary test seam is `_call_claude()`. By patching this function, tests control exactly what the service receives from the AI layer without making network calls. For the `ImportError` path specifically, `sys.modules["anthropic"] = None` is used — this tests the actual deferred-import code path through Python's import machinery, not a mock of the function.

Environment variables are controlled per-test using pytest's `monkeypatch` fixture, which restores the original state after each test automatically.

### Test categories

| Category | What is proven |
|---|---|
| Missing API key | Fallback fires before any network attempt; `_call_claude` is never invoked |
| ImportError | Deferred import failure is caught and contained |
| Malformed JSON | `JSONDecodeError` is caught; fallback returned |
| Valid response | Happy path returns correct shape, values, and types |
| Confidence coercion | String `"0.89"` from Claude is coerced to `float` |
| Missing required fields | Partial response is rejected; fallback returned |
| Invalid `risk_level` | Out-of-set value is rejected; fallback returned |
| Wrong `explainability` type | Non-list value is rejected; fallback returned |
| Generic API exception | Network/timeout errors are contained; fallback returned |
| Fallback shape contract | Fallback always satisfies the full response contract |
| Fallback independence | Mutating a returned fallback dict cannot corrupt future calls |

---

## Current Limitations

The following limitations apply as of the current implementation. They are documented here to prevent future engineers from treating the current state as the intended final state.

**The AI layer is not yet wired into any production route.** `generate_ai_insight()` exists in `services/ai_insight_service.py` and is covered by tests, but no API endpoint calls it. The existing `POST /insight/generate` route continues to use the template-based `InsightService`. The AI layer is available for integration but not yet integrated.

**Explainability is generated by Claude but not persisted.** The `explainability` list returned by the service is never written to the database. The `GeneratedInsight` ORM model does not have an `explainability` column. Until that column is added and the service result is persisted, explainability is ephemeral — it exists only in the API response for the duration of that request.

**The governance approval workflow is not yet connected.** High-confidence, high-severity insights should route to the `ApprovalRequests` table for human review before triggering outbound actions. That table does not exist yet (Sprint 1). The AI layer has no mechanism to request approval or block on it.

**No human review queue exists.** The fallback signal (`confidence == 0.0`, `risk_level == "unknown"`) is machine-detectable, but there is currently no queue, dashboard panel, or notification that routes fallback-state insights to a human reviewer. Fallback events are logged but not acted upon.

**Feature flags are not implemented.** There is no mechanism to enable or disable the AI layer per environment, per cohort, or per request. The layer is either present (if `ANTHROPIC_API_KEY` is set) or in fallback mode (if it is not). Granular control requires a feature flag system that does not yet exist.

---

## Next Integration Phase

The following steps represent the planned integration sequence. Each step is additive — no existing file is modified until the new capability is ready to be connected.

**1. Feature-flag route integration**
Create a new route `POST /insight/generate/ai` (or extend the existing route with an `ai=true` query parameter behind an env-flag check) that calls `generate_ai_insight()` with data loaded by the existing `InsightService`. The existing route remains unchanged. This allows the AI and template paths to run in parallel for comparison before the template path is retired.

**2. Explainability rendering in the frontend**
The frontend's `InsightCard` component already renders `explanation` and `recommended_action` fields. Extending it to render `explainability` as a list of bullet points requires a frontend change only — no backend modification. The response contract already includes the field.

**3. Approval and governance workflow connection**
Once the `ApprovalRequests` table exists (Sprint 1), insights with `risk_level` of `high` or `critical` should create an `ApprovalRequest` before any downstream action is taken. The AI insight layer will pass its `risk_level` and `confidence` to `GovernanceApprovalService.request_approval()` rather than routing directly to outbound delivery.

**4. Historical insight persistence**
Add an `explainability_json` column to `AI_ChatBot_GeneratedInsights` via an Alembic migration. Modify `InsightService.save_insights()` to persist the `explainability` list from the AI response alongside the existing insight fields. This makes explainability part of the forensic audit trail for any insight event.

**5. Audit-chain integration**
Log an `EngagementEvent` with `event_type = EventType.INSIGHT_GENERATED` for every successful AI insight call, linked to the student's `user_id`. This closes the audit trail: the full lifecycle from KPI signal → AI insight → governance decision → outbound action becomes reconstructable from the `EngagementEvents` table using `trigger_id` as the join key.
