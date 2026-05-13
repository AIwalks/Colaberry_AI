# AI Route Validation
**Colaberry Sentinel OS | Internal Engineering Document**
**Status: Validated**
**Last updated: 2026-05-11**

---

## Validation Summary

End-to-end validation of the AI insight route was completed successfully against a live Anthropic Claude inference call.

The following was confirmed:

- **Live Claude inference** — the route successfully called the Anthropic Claude API and received a structured, contract-compliant response containing a risk assessment, confidence score, explainability reasoning, and actionable mentor guidance.
- **Feature-flagged route operational** — `POST /insight/generate/ai` is correctly gated behind the `ENABLE_AI_INSIGHTS` environment variable. With the flag set to `true` and a valid API key present, the route produces genuine AI inference. With the flag absent or set to any other value, the route returns a clean disabled response with no AI call attempted.
- **Deterministic fallback path verified earlier** — the fallback path (`confidence=0.0`, `risk_level="unknown"`) was verified in isolation via unit tests prior to live validation. The unit test suite (13 tests in `tests/unit/test_ai_insight_service.py`) covers every failure mode: missing API key, SDK import error, malformed JSON, validation failure, and network exceptions. All 13 pass deterministically without real API calls.
- **No orchestration pipeline changes required** — the existing trigger processing, message delivery, and engagement logging pipeline was not modified. The AI layer operates as a parallel enrichment path.

---

## Environment Used

| Parameter | Value |
|---|---|
| Environment | Local development |
| Backend | FastAPI via `uvicorn` |
| Database | SQLite (`local.db`) |
| Feature flag | `ENABLE_AI_INSIGHTS=true` |
| API auth | `API_KEY=demo-key` (development value) |
| Anthropic key | Development credential — not stored in repo |
| Model | `claude-sonnet-4-6` |

Production credentials will be managed separately via environment-specific secret management. No credentials are stored in this repository or in any committed file.

---

## Endpoint Tested

```
POST /insight/generate/ai
```

This route is **additive-only**. It was appended to `api/routes/insight.py` without modifying any existing handler. The existing `POST /insight/generate` route is untouched and continues to operate identically to its pre-AI state.

The new route reuses the same data loading methods as the deterministic insight engine — `InsightService.load_kpis()` and `InsightService.load_fingerprints()` — so the AI layer receives the same KPI and behavioral fingerprint data that the template-based engine has always processed. No new database queries or data models were required.

Authentication is inherited from the `insight_router` registration in `app/main.py`, which applies `require_api_key` to all routes in the router. No changes to `main.py` were required.

---

## Test Request

```json
{
  "entity_id": "student_101",
  "entity_type": "student"
}
```

Student `student_101` has seeded KPI data covering login frequency decline and session duration drop patterns, and a behavioral fingerprint at `score=1.0` in the disengagement pattern. This student profile was chosen because it presents a high-signal, interpretable dataset — the AI response can be evaluated against known ground truth.

---

## Validation Result

The live response confirmed the following:

| Field | Value |
|---|---|
| `ai_enabled` | `true` |
| `analyzed_kpis` | 3 |
| `analyzed_fingerprints` | 1 |
| `risk_level` | `high` |
| `confidence` | `0.86` |

The response satisfied the full response contract defined in `docs/AI_INSIGHT_LAYER.md`:

- All five required fields present: `summary`, `risk_level`, `confidence`, `recommended_action`, `explainability`
- `risk_level` was within the valid set: `{low, medium, high, critical}`
- `confidence` was a float in range `(0.0, 1.0)` — not the fallback sentinel value of `0.0`
- `explainability` was a list of at least two specific, data-grounded reasons
- `recommended_action` contained specific mentor guidance referenced to the student's signals, not generic advice

The AI response was structurally validated by `_validate()` before it reached the route handler. The route then mapped it to the `AIInsightGenerateResponse` schema and serialized it correctly.

**Observed AI behavior quality:**

- The model correctly interpreted the KPI confidence values as indicators of pattern strength, not mere metadata.
- The model identified the disengagement risk classification without being prompted with the label — it inferred it from the KPI signal names and fingerprint score.
- The explainability reasoning referenced specific confidence percentages and sample sizes drawn from the input, demonstrating that the model processed the structured prompt rather than generating generic text.
- The recommended action was time-bound and role-specific ("within 48 hours," directed at a mentor), consistent with the system prompt's instruction to avoid generic advice.
- The model did not hallucinate workflow actions or reference systems (approval queues, outbound triggers) that do not exist in the prompt context.

---

## Example AI Behaviors Observed

**Login frequency interpretation:** The model identified a login frequency KPI carrying a high-confidence disengagement pattern and correctly framed it as a leading indicator — not a confirmed outcome — with appropriate uncertainty expressed in the confidence score rather than in hedged language.

**Session duration risk interpretation:** A session duration drop KPI was interpreted as corroborating evidence for avoidance behavior, correctly weighted below the login frequency signal (lower sample size, lower confidence). The model reflected this weighting in its composite confidence score.

**Behavioral fingerprint correlation:** The disengagement fingerprint at score `1.0` — meaning all disengagement thresholds were matched — was correctly treated as a confirming signal rather than an independent risk factor. The model synthesized the fingerprint with the KPI signals rather than treating them as separate observations.

**Recommended mentor action:** The model produced a specific, actionable outreach recommendation that referenced the student's signal pattern and included a time constraint appropriate to a high-risk classification. The action was directed at a mentor, consistent with the system prompt's stated audience.

---

## Architectural Validation

The live test proved the following architectural properties:

**Feature flag isolation works.** Setting `ENABLE_AI_INSIGHTS=true` enabled the AI path. The route correctly bypasses data loading and AI inference when the flag is absent or false, returning a `200` response with `ai_enabled=false` and an empty insight list. This was verified at the route level in unit tests and confirmed by the disabled-state behavior prior to enabling the flag.

**Fallback isolation works.** The `generate_ai_insight()` function never raises. Any failure — network, API key, malformed JSON, validation error — returns the fallback dict (`confidence=0.0`, `risk_level="unknown"`) without propagating an exception to the route. This was verified by the 13-test deterministic suite and is structurally guaranteed by the `try/except` design in `services/ai_insight_service.py`.

**Live AI inference works end-to-end.** The full call chain — request → auth → feature flag check → data load → `generate_ai_insight()` → `_call_claude()` → `_validate()` → response mapping → Pydantic serialization — completed successfully with a semantically correct response.

**Auth enforcement works.** The route enforces the `X-Api-Key` header via the inherited `require_api_key` dependency. Requests without the correct key return `HTTP 403` before the route handler executes. This was verified in two unit tests covering missing and incorrect keys.

**Existing deterministic routes remain stable.** The `POST /insight/generate` route was not modified. Its unit tests (31 tests in `tests/unit/test_insight_route.py`) all pass after the AI route was added. The route continues to use the template-based `InsightGenerator` and `InsightService` pipeline unchanged.

**No orchestration pipeline changes were required.** `trigger_processing_service.py`, `mentor_message_service.py`, `outbound_delivery_service.py`, and `trigger_worker.py` were not modified. The AI layer adds a new route and a new service. It has no import dependency on any of these files, and they have no import dependency on it.

---

## Known Remaining Work

The following items are documented as incomplete as of this validation. They are tracked here to prevent future engineers from treating the current validated state as the final intended state.

**Frontend explainability rendering pending.** The `explainability` list is returned in the API response but the `InsightCard` component in `frontend/src/App.tsx` does not yet render it as a bullet list. The `explanation` field (a joined string of the list) is rendered correctly. Rendering the list natively requires a frontend change only — no backend modification.

**AI insight persistence pending.** The AI response is returned to the caller but not written to the database. The `GeneratedInsight` ORM model does not have an `explainability_json` column. Until an Alembic migration adds this column and `InsightService.save_insights()` is extended to persist AI results, AI insights are ephemeral — they exist only for the duration of the API response.

**Governance approval workflow pending.** High-confidence, high-severity AI insights (`risk_level` of `high` or `critical`) should route to an `ApprovalRequests` table for human review before any downstream action is triggered. That table does not yet exist. The AI layer currently returns results directly to the caller with no approval gate.

**Audit-chain persistence pending.** No `EngagementEvent` is logged for a successful AI insight call. The full lifecycle from KPI signal → AI insight → governance decision → outbound action is not yet reconstructable from the `EngagementEvents` table. This will require a new `EventType.INSIGHT_GENERATED` value and a log write in the route handler.

**Production secret management pending.** The `ANTHROPIC_API_KEY` used for this validation was a development credential set in the local environment. Production deployments require a formal secret management solution. The key must not be committed to the repository, stored in `.env` files under version control, or passed through application configuration files.

---

## Conclusion

The Colaberry Sentinel OS MVP has successfully transitioned from a template-only insight engine to a governed, live AI-assisted inference architecture.

Prior to this work, the system's `POST /insight/generate` route returned pre-written strings from a database column and labelled them AI-generated. That claim was not accurate.

The system now has a second, parallel route — `POST /insight/generate/ai` — that calls the Anthropic Claude API, receives a structured JSON response, validates it against a documented contract, and returns an explainable, confidence-scored insight with traceable reasoning. The AI layer is isolated, feature-flagged, fallback-safe, auth-enforced, and test-covered. It does not modify the existing deterministic pipeline.

The system can now honestly claim AI-assisted reasoning on the student data it observes.
