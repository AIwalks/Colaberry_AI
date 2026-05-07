# RISK REPORT
**Colaberry Sentinel OS — Phase 5 Risk Analysis**
**Date: 2026-05-07**

---

## TOP ARCHITECTURAL RISKS

### AR-1: Governance Gap in Running System (CRITICAL)
The trigger pipeline currently executes without an approval gate. High-severity triggers fire and send messages automatically. The spec explicitly requires approval-gated execution. **The system is architecturally non-compliant with its own specification.**

**Mitigation:** Build GovernanceApprovalService (Sprint 1)

### AR-2: No Observation Layer (HIGH)
The core system intelligence depends on observing the production SQL Server, but no observation service exists. The system can evaluate pre-existing KPI columns but cannot discover new patterns, map trigger chains, or analyze query performance.

**Mitigation:** Build ObservationService (Sprint 2)

### AR-3: Non-Invasive Overlay Discipline (MEDIUM)
The additive-only constraint is well-implemented in the overlay design. The risk is future pressure to "just fix this in production directly." The `database_safety.md` directive exists but has no enforcement mechanism.

**Mitigation:** Add automated pre-commit check that blocks SQL migrations containing ALTER/DROP against production table names.

---

## TOP SCALABILITY RISKS

### SR-1: Trigger Worker Single-Instance (MEDIUM)
`trigger_worker.py` runs as a single process. If trigger volume increases significantly, a single worker becomes a bottleneck.

**Mitigation (future):** Add Celery or asyncio-based worker pool. Not needed at current volume.

### SR-2: ConversationState by PhoneNumber (LOW)
`ConversationState` is keyed by `PhoneNumber` (PK). This is fine for current scale. At large scale, a phone number can be reassigned to a different student, creating stale state.

**Mitigation:** Add `UserID` to `ConversationState` as a secondary key and validate on lookup.

### SR-3: StateJSON Blob Growth (LOW)
`ConversationState.StateJSON` stores the full conversation context as a JSON blob. Long conversations will grow indefinitely.

**Mitigation:** Implement context window trimming in `MentorMessageService`.

---

## TOP GOVERNANCE RISKS

### GR-1: Constitutional Documents Claim System is Complete (CRITICAL)
Files like `final_operational_completion_and_constitutional_certification.md` and `final_enterprise_readiness_and_global_go_live_authorization.md` assert the system is complete and ready for production. This creates a false governance record.

**Mitigation:** Archive or delete these files. Document actual system state truthfully.

### GR-2: No Human-Reviewable Pending Queue (HIGH)
When the approval gate is built, humans need a UI to see what requires approval. Without this, the approval system is unusable in practice.

**Mitigation:** Build admin dashboard as Sprint 4 priority.

### GR-3: Directive Versioning Not Enforced (MEDIUM)
Directives have a `version` field in the database, but there is no enforcement that changes to directive files in `/directives` are synced to the database, or vice versa. The "living documents" principle creates drift risk.

**Mitigation:** Build a directive sync check as part of CI.

---

## TOP REPLAY/AUDIT RISKS

### RAR-1: "Replay-Safe" Guarantee Cannot Be Fulfilled (CRITICAL)
42+ constitutional documents promise "replay-safe" operations. The system has no event sourcing infrastructure to fulfill this guarantee.

**Mitigation:** Redefine "replay-safe" as "forensically reconstructable from audit log." Update terminology. Do not build event sourcing unless there is a genuine operational need.

### RAR-2: Audit Log Gap at Message Boundary (MEDIUM)
The audit log captures outbound messages (`ChatBotAuditLog`). However, the linkage between a `TriggeredUser.CBM_ID` and the corresponding `ChatBotAuditLog.CBM_ID` depends on the caller correctly passing CBM_ID through. If the caller omits it, the audit chain breaks.

**Mitigation:** Add a test that verifies CBM_ID is present in every audit log entry produced by a trigger.

### RAR-3: No Tamper Detection on Audit Log (LOW)
Audit log rows are append-only by design but there is no cryptographic tamper detection. A database administrator with write access could modify rows.

**Mitigation (future):** For high-compliance environments, consider a signed audit chain. Not required for MVP.

---

## TOP MAINTAINABILITY RISKS

### MR-1: 50+ Duplicate Doctrine Files (CRITICAL)
The `/integration` constitutional doctrine files create extreme maintenance burden. Any change to governance philosophy requires updating 50 files instead of 1.

**Mitigation:** Delete clone files (see REMOVE_OR_DEFER_LIST.md)

### MR-2: No Canonical Vocabulary (HIGH)
The same concept is described with 30+ different noun variations across documents. New contributors cannot learn the system vocabulary because there is no canonical glossary.

**Mitigation:** Use the vocabulary table in CANONICAL_ARCHITECTURE.md as the canonical reference.

### MR-3: Implementation Plan Duplication (MEDIUM)
`execution/implementation_plan.md` and `implementation/implementation_roadmap.md` overlap. The roadmap is the authoritative document.

**Mitigation:** Delete `execution/implementation_plan.md` or merge its unique content into the roadmap.

---

## TOP OVER-ENGINEERING RISKS

### OER-1: Constitutional Framework Exceeds System Scope by ~10 Orders of Magnitude (CRITICAL)
A student engagement chatbot does not require "species survivability" governance. The over-specification:
1. Attracts more over-specification as future contributors try to "match the existing level"
2. Hides the actual system in a sea of irrelevant language
3. Makes realistic planning impossible because the stated requirements are infinite

**Mitigation:** Archive constitutional doctrine. Return to spec-driven development.

### OER-2: 10-Phase Implementation Roadmap for a Working MVP (MODERATE)
Phase 0–1 is in progress. Phases 2–10 describe capabilities years away. The roadmap is valuable directionally but risks creating the impression of massive ongoing construction without clear phase gates.

**Mitigation:** Focus on Phase 0–4. Treat Phases 5–10 as aspirational appendix.

### OER-3: Governance Review Board Before Basic Approval UI (MODERATE)
`operations/governance_review_board_model.md` describes a multi-person governance board. The system does not yet have a single human approval UI. Building a board process before the tool is premature.

**Mitigation:** Build the tool first, then formalize the process around it.

---

## TOP AMBIGUITY RISKS

### AMR-1: "Agent" Means Multiple Things (HIGH)
In this repo, "agent" refers to:
1. `AgentID` in `TriggerRule` / `TriggeredUser` — a database concept for routing
2. The planned multi-agent debate system — future AI agents
3. Claude Code agents — the development tool
4. `/agents` folder — placeholder for AI personas

This ambiguity will cause implementation confusion.

**Mitigation:** Define "Agent" in the canonical vocabulary. Use distinct terms: `TriggerAgent` (database routing), `AIAgent` (LLM agent), `DevAgent` (Claude Code tool).

### AMR-2: "Replay" Is Used for Two Different Concepts (HIGH)
"Replay" appears to mean:
1. "We can audit what happened" (achievable with current audit tables)
2. "We can re-execute the event stream to reconstruct state" (requires event sourcing)

The documents use both meanings interchangeably.

**Mitigation:** Define replay as "audit reconstruction" only. If event sourcing is ever needed, use the term "event sourcing" explicitly.

### AMR-3: "Production" Is Ambiguous (MEDIUM)
The system distinguishes dev/staging/production, but it's unclear whether "production" means:
1. The Colaberry SQL Server (always production, read-only for most tables)
2. The overlay system deployed in production mode

**Mitigation:** Use "production SQL Server" and "production deployment" consistently in all documentation.
