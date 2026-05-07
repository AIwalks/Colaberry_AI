# REMOVE OR DEFER LIST — MAXIMUM RIGOR EDITION
**Colaberry Sentinel OS | Date: 2026-05-07**

---

## HOW THE DOCTRINE INFLATION HAPPENED

This is not a mystery. The pattern is mechanically predictable:

1. A legitimate governance document was created (e.g., `integration/platform_governance_framework.md`)
2. An AI assistant was asked to "create a constitutional framework" or "ensure governance compliance"
3. The AI generated a second document using the same 22-section template with noun substitution
4. The second document was accepted without review
5. The AI was asked again for governance validation, generating a third document
6. Repeat 40 times

The smoking gun: all 42 files share **identical invariants** (word-for-word), **identical anti-patterns** (word-for-word), and **identical success criteria** (word-for-word). Only the compound noun in the title changes. No human writes 42 files with identical invariant lists. This is AI self-amplification without editorial control.

The root cause is not malice or incompetence. It is an AI assistant that:
- Treats "write a document" as an independent action with no awareness of existing documents
- Has no shared context across sessions about what already exists
- Defaults to generating more structure when asked to validate existing structure

**The fix is not to write better documents. The fix is to DELETE documents and add a rule to CLAUDE.md: no governance documents without a stated gap in CONFLICT_ANALYSIS.md.**

---

## CLASSIFICATION CRITERIA

| Class | Meaning | Action |
|---|---|---|
| **REMAIN** | Governs a real, unique concern not covered elsewhere. Readable by engineers. | Keep as-is or minor cleanup |
| **MERGE** | Contains real content but overlaps with another surviving file | Merge into the survivor, delete this file |
| **ARCHIVE** | May contain valid reasoning buried under doctrine language; not needed for operations | Move to `/archive/doctrine/` |
| **DELETE** | Identical or near-identical clone with no unique content | Delete immediately |

---

## FILES TO REMAIN (15 FILES)

These files contain unique, actionable engineering content.

### Core Specification
| File | Why It Stays |
|---|---|
| `spec/01_requirements.md` | Source of truth for FR-GOV-001, FR-EXEC-001. Referenced in tests. |
| `spec/02_architecture.md` | Defines bounded contexts, service boundaries, data flow |
| `spec/03_data_model.md` | Canonical entity definitions (where they conflict with models.py, models.py wins) |
| `spec/04_security.md` | Security requirements (auth, PII, RBAC roadmap) |
| `spec/05_api_contract.md` | API endpoint contracts |

### Integration (Legitimately Unique)
| File | Why It Stays |
|---|---|
| `integration/database_observation_and_intelligence_architecture.md` | Defines the overlay strategy — how to read SQL Server DMVs without modifying production tables |
| `integration/student_engagement_flow.md` | Describes the end-to-end trigger → message → response lifecycle |
| `integration/deployment_configuration.md` | Env var list, SQLite vs MSSQL configuration, Twilio credentials |
| `integration/alembic_migration_strategy.md` | Additive-only constraint, migration naming, rollback policy |
| `integration/outbound_delivery_channels.md` | Twilio SMS/WhatsApp, SMTP, Voice — what is implemented vs. stub |
| `integration/event_model_and_engagement_tracking.md` | EngagementEvent taxonomy, DeliveryLog, AuditLog — what is actually logged |
| `integration/platform_operational_maturity_model.md` | 10-phase roadmap (strategic direction only; ignore compliance-grade language) |
| `integration/student_response_matching_strategy.md` | Thread ID vs. time-proximity matching — the design rationale |

### Governing Documents
| File | Why It Stays |
|---|---|
| `CLAUDE.md` | The actual operating contract. Governs AI behavior. Not negotiable. |
| `audit/` (all 9 files) | This audit IS the governance documentation going forward |

---

## FILES TO MERGE (4 FILES)

These contain real content that belongs inside a surviving file.

| File | Merge Into | Content to Extract |
|---|---|---|
| `integration/trigger_worker_configuration.md` | `integration/deployment_configuration.md` | Worker poll interval, retry count, cooldown settings |
| `integration/api_authentication_model.md` | `spec/04_security.md` | API key header name, test bypass instructions |
| `directives/student_response_tracking_contract.md` | `integration/student_response_matching_strategy.md` | Match method priority order, confidence thresholds |
| `directives/system_behavior_directives.md` | `CLAUDE.md` | The 6 runtime invariants buried in this file are real; add to CLAUDE.md "Runtime Behavior Rules" section |

**Merge process:** Extract the 1–3 useful paragraphs. Paste into the target file. Delete the source file. Do not preserve the 22-section wrapper.

---

## FILES TO ARCHIVE (5 FILES)

These contain valid philosophical reasoning that motivated the project, but are not operational documents. They should not be deleted outright because they capture design intent from the project's founding period.

| File | Why Archive (Not Delete) | Archive Location |
|---|---|---|
| `integration/platform_governance_framework.md` | Contains the original motivation for the approval gate (FR-GOV-001). Useful for understanding *why* governance exists. | `/archive/doctrine/` |
| `integration/ai_agent_behavioral_constraints.md` | Contains valid human-oversight principles before they were inflated. | `/archive/doctrine/` |
| `integration/event_driven_orchestration_model.md` | Contains the aspirational event sourcing vision (useful for Phase 6–7 planning). | `/archive/doctrine/` |
| `implementation/implementation_roadmap.md` | 10-phase roadmap is useful as strategic direction; too long for sprint planning. | Add header: "STRATEGIC DIRECTION ONLY — see audit/IMPLEMENTATION_SEQUENCE.md for tactical planning" |
| `implementation/readiness_gates_checklist.md` | Enterprise maturity gates are aspirational; document the intent. | `/archive/doctrine/` |

---

## FILES TO DELETE (38 FILES)

These are word-substitution clones with zero unique content. Every invariant, every anti-pattern, every success criterion is copied from the template. No unique engineering decision exists in any of them.

**Verification method:** `grep -l "Execution integrity is non-negotiable" integration/*.md | wc -l` returns 37+. If every file contains the same sentence, no file is unique.

### The Clone Set — DELETE ALL

```
integration/final_absolute_constitutional_species_governance_and_supremacy_authorization.md
integration/final_absolute_execution_supremacy_and_constitutional_authorization_covenant.md
integration/final_absolute_operational_permanence_and_constitutional_governance_codex.md
integration/final_agent_behavioral_constitution_and_governance_closure.md
integration/final_civilization_resilience_and_constitutional_permanence_framework.md
integration/final_constitutional_deployment_gateway_and_closure_protocol.md
integration/final_constitutional_execution_and_governance_permanence_codex.md
integration/final_constitutional_integrity_and_species_preservation_authorization.md
integration/final_enterprise_readiness_and_global_go_live_authorization.md
integration/final_eternal_governance_and_constitutional_preservation_covenant.md
integration/final_eternal_institutional_memory_and_constitutional_permanence.md
integration/final_execution_governance_and_constitutional_supremacy_covenant.md
integration/final_global_deployment_authorization_and_constitutional_governance.md
integration/final_governance_constitutional_closure_and_permanence_authorization.md
integration/final_human_oversight_and_constitutional_governance_framework.md
integration/final_institutional_memory_and_constitutional_closure_covenant.md
integration/final_operational_closure_and_constitutional_governance_permanence.md
integration/final_operational_completion_and_constitutional_certification.md
integration/final_operational_permanence_and_constitutional_deployment_gateway.md
integration/final_permanent_agent_behavioral_architecture_and_governance_closure.md
integration/final_permanent_constitutional_agent_governance_and_deployment_closure.md
integration/final_permanent_execution_framework_and_governance_authorization.md
integration/final_permanent_operational_closure_and_constitutional_governance.md
integration/final_platform_constitutional_closure_and_governance_authorization.md
integration/final_post_humanity_replay_safe_constitutional_framework.md
integration/final_replay_safe_species_continuity_and_eternal_constitutional_humanity_closure.md
integration/final_species_continuity_and_constitutional_governance_preservation.md
integration/final_species_survivability_and_constitutional_permanence_framework.md
integration/final_supreme_agent_behavioral_constitution_and_governance.md
integration/final_supreme_constitutional_framework_and_governance_authorization.md
integration/final_system_constitutional_permanence_and_governance_closure.md
integration/final_system_deployment_and_constitutional_governance_finalization.md
integration/global_enterprise_operational_launch_manifest.md
integration/permanent_constitutional_closure_and_governance_framework.md
integration/permanent_operational_framework_and_constitutional_governance.md
integration/permanent_system_governance_and_constitutional_deployment_closure.md
integration/supreme_constitutional_governance_and_deployment_authorization.md
execution/implementation_plan.md
```

Rationale for `execution/implementation_plan.md`: Exact partial duplicate of `audit/IMPLEMENTATION_SEQUENCE.md`. The IMPLEMENTATION_SEQUENCE.md version is more complete and more recent. Two diverging plans create confusion about which is authoritative.

---

## WHAT REMAINS AFTER CLEANUP

```
/spec/                (5 files — authoritative requirements and contracts)
/integration/         (8 files — unique operational content)
/implementation/      (1 file — strategic roadmap, not sprint plan)
/archive/doctrine/    (4 files — historical reference, not operational)
/directives/          (files with unique runtime behavior content after merge)
/audit/               (9 files — this audit, now the governance layer)
CLAUDE.md             (the operating contract)
```

Total: ~28 files. Down from 90+. Every remaining file has a unique purpose.

---

## HOW TO PREVENT RECURRENCE

Add the following to `CLAUDE.md` under "Document Creation Rules":

```
## Document Creation Rules

1. Before creating any governance, architecture, or compliance document,
   search for an existing document that covers the same topic.
   If one exists, edit it. Do not create a new file.

2. No governance document may be created without identifying a specific gap
   in audit/CONFLICT_ANALYSIS.md that it addresses.

3. Constitutional, civilizational, species-level, or "eternal" language
   is prohibited in engineering documentation. Documents using these words
   will be deleted.

4. Every new file in /integration/ requires a one-line entry in audit/README.md
   explaining what unique content it contains and what question it answers.

5. Documents may not claim to be "final", "supreme", "ultimate", or "permanent".
   These adjectives do not survive the next sprint.
```

---

## DELETION SCRIPT

```bash
# Run from repo root. Review list before executing.
# Estimated time: 60 minutes including git commit.

DELETE_LIST=(
  "integration/final_absolute_constitutional_species_governance_and_supremacy_authorization.md"
  "integration/final_absolute_execution_supremacy_and_constitutional_authorization_covenant.md"
  "integration/final_absolute_operational_permanence_and_constitutional_governance_codex.md"
  "integration/final_agent_behavioral_constitution_and_governance_closure.md"
  "integration/final_civilization_resilience_and_constitutional_permanence_framework.md"
  "integration/final_constitutional_deployment_gateway_and_closure_protocol.md"
  "integration/final_constitutional_execution_and_governance_permanence_codex.md"
  "integration/final_constitutional_integrity_and_species_preservation_authorization.md"
  "integration/final_enterprise_readiness_and_global_go_live_authorization.md"
  "integration/final_eternal_governance_and_constitutional_preservation_covenant.md"
  "integration/final_eternal_institutional_memory_and_constitutional_permanence.md"
  "integration/final_execution_governance_and_constitutional_supremacy_covenant.md"
  "integration/final_global_deployment_authorization_and_constitutional_governance.md"
  "integration/final_governance_constitutional_closure_and_permanence_authorization.md"
  "integration/final_human_oversight_and_constitutional_governance_framework.md"
  "integration/final_institutional_memory_and_constitutional_closure_covenant.md"
  "integration/final_operational_closure_and_constitutional_governance_permanence.md"
  "integration/final_operational_completion_and_constitutional_certification.md"
  "integration/final_operational_permanence_and_constitutional_deployment_gateway.md"
  "integration/final_permanent_agent_behavioral_architecture_and_governance_closure.md"
  "integration/final_permanent_constitutional_agent_governance_and_deployment_closure.md"
  "integration/final_permanent_execution_framework_and_governance_authorization.md"
  "integration/final_permanent_operational_closure_and_constitutional_governance.md"
  "integration/final_platform_constitutional_closure_and_governance_authorization.md"
  "integration/final_post_humanity_replay_safe_constitutional_framework.md"
  "integration/final_replay_safe_species_continuity_and_eternal_constitutional_humanity_closure.md"
  "integration/final_species_continuity_and_constitutional_governance_preservation.md"
  "integration/final_species_survivability_and_constitutional_permanence_framework.md"
  "integration/final_supreme_agent_behavioral_constitution_and_governance.md"
  "integration/final_supreme_constitutional_framework_and_governance_authorization.md"
  "integration/final_system_constitutional_permanence_and_governance_closure.md"
  "integration/final_system_deployment_and_constitutional_governance_finalization.md"
  "integration/global_enterprise_operational_launch_manifest.md"
  "integration/permanent_constitutional_closure_and_governance_framework.md"
  "integration/permanent_operational_framework_and_constitutional_governance.md"
  "integration/permanent_system_governance_and_constitutional_deployment_closure.md"
  "integration/supreme_constitutional_governance_and_deployment_authorization.md"
  "execution/implementation_plan.md"
)

for f in "${DELETE_LIST[@]}"; do
  git rm "$f" 2>/dev/null || rm -f "$f"
  echo "Deleted: $f"
done

mkdir -p archive/doctrine
for f in \
  "integration/platform_governance_framework.md" \
  "integration/ai_agent_behavioral_constraints.md" \
  "integration/event_driven_orchestration_model.md" \
  "implementation/readiness_gates_checklist.md"
do
  git mv "$f" archive/doctrine/ 2>/dev/null || mv "$f" archive/doctrine/
  echo "Archived: $f"
done

git commit -m "chore: delete 37 doctrine clone files; archive 4 historical design docs

Rationale: All 37 deleted files are word-substitution clones of a common
22-section template. Zero unique engineering content exists in any of them.
The 4 archived files contain valid founding intent buried under inflated
language. See audit/REMOVE_OR_DEFER_LIST.md for full classification."
```
