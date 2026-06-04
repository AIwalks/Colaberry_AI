# DOMAIN MODEL — MAXIMUM RIGOR EDITION
**Colaberry Sentinel OS | Date: 2026-05-07**

---

## CORE AGGREGATE: THE TRIGGER EVENT

The central unit of work in this system is a single trigger event lifecycle:

```
TriggerRule evaluated against Student KPI
    → TriggeredUser row created (CBM_ID is the system-wide join key)
    → Message generated (template from DB or LLM — to be built)
    → TriggeredUser atomically claimed (Completed = 0 → 1)
    → Message delivered (OutboundDeliveryService → Twilio)
    → DeliveryLog row created
    → TriggeredUser.DeliverySucceeded written
    → EngagementEvent rows written throughout
    → ChatBotAuditLog rows written throughout
    → Student replies → StudentResponse row links reply to CBM_ID
```

Everything in the system serves this flow. Every table supports this flow. **CBM_ID is the system spine.**

---

## ENTITY DEFINITIONS WITH FIELD TRUTH

### Entity 1: TriggerData (READ-ONLY PRODUCTION TABLE)
```
Table: AI_ChatBot_TriggerData
Source: Production SQL Server (do NOT modify)
Model: services/models.py:38

Fields:
  UserID              INTEGER PK  — student identifier (join key everywhere)
  UserName            VARCHAR(100)
  FirstName           VARCHAR(50)
  LastName            VARCHAR(50)
  Email               VARCHAR(256)  nullable
  PhoneNumber         VARCHAR(20)   nullable  — used by OutboundDeliveryService
  ActiveStatus        VARCHAR(10)   nullable  — used by StudentStatusFetcher
  StatusI             VARCHAR(10)   nullable
  StatusII            VARCHAR(4000) nullable

KPI Columns (read by TriggerEvaluator via getattr):
  Past10DaysLogon          INTEGER
  LastActivityDays         INTEGER
  LastLoginDays            INTEGER
  DaysInStatus             INTEGER
  HWsBehind                INTEGER
  AttendancePercentage     FLOAT
  AvgHWScore               FLOAT
  AvgEffRating             FLOAT
  NoOfAssignmentsSubmitted INTEGER
  TotalNoOfAssignments     INTEGER
  Total_Payments           FLOAT
  PaymentBalance           INTEGER
  IsClassActive            INTEGER
```

### Entity 2: TriggerRule (READ-ONLY PRODUCTION TABLE)
```
Table: AI_ChatBot_TriggerRules
Source: Production SQL Server (do NOT modify)
Model: services/models.py:87

Fields:
  CB_ID                    INTEGER PK  — rule identifier
  TriggerType              VARCHAR     — student cohort: All/Capstone/InClass/etc.
  KPI                      VARCHAR     — name of TriggerData column to evaluate
  Severity                 INTEGER     — weight (used for prioritization)
  TriggerLow               NUMERIC(10,2) — threshold: value below this = "Low"
  TriggerHigh              NUMERIC(10,2) — threshold: value above this = "High"
  ChatGPTPromptLowTrigger  TEXT  — message template for Low trigger (NOT AI output)
  ChatGPTPromptHighTrigger TEXT  — message template for High trigger (NOT AI output)
  AgentID                  INTEGER     — routing to Agent_Agents table

NOTE: ChatGPTPromptLow/HighTrigger are PRE-WRITTEN STRINGS, not LLM prompts.
The word "ChatGPT" in the column name is a legacy label, not a runtime call.
```

### Entity 3: TriggeredUser (READ + WRITE — CENTRAL ENTITY)
```
Table: AI_ChatBot_TriggeredUsers
Model: services/models.py:119

Fields:
  CBM_ID           INTEGER PK autoincrement  — THE SYSTEM SPINE
  CB_ID            INTEGER FK→TriggerRule.CB_ID
  UserID           INTEGER FK-style→TriggerData.UserID
  TriggerType      VARCHAR    — denormalized from rule
  TriggerLevel     VARCHAR    — "Low" | "High" | "Unknown" | "None"
  KPI              VARCHAR    — denormalized from rule
  Severity         INTEGER    — denormalized from rule
  InsertDate       DATETIME   — when trigger was recorded
  Completed        INTEGER    — 0=pending, 1=claimed (atomic claim via RETURNING)
  CompletedDate    DATETIME   — when claimed
  AgentID          INTEGER    — denormalized from rule
  DeliverySucceeded BOOLEAN   nullable  — True=sent, False=failed, None=not attempted

Invariants:
- Completed 0→1 transition is atomic (UPDATE ... RETURNING CBM_ID)
- Once Completed=1, no worker will re-process (prevents duplicate sends)
- DeliverySucceeded is written AFTER delivery attempt
```

### Entity 4: ConversationState (READ + WRITE)
```
Table: AI_ChatBot_ConversationState
Model: services/models.py:161

Fields:
  PhoneNumber  VARCHAR(50) PK  — student contact identifier
  Email        VARCHAR(255)   nullable
  Channel      VARCHAR(50)    nullable  — whatsapp/sms/email/etc.
  StateJSON    TEXT           nullable  — full conversation blob (no size limit)
  LastUpdated  DATETIME       nullable

RISK: PhoneNumber as PK means phone number reassignment creates stale state.
RISK: StateJSON is unbounded; long conversations grow indefinitely.
```

### Entity 5: ChatBotAuditLog (APPEND-ONLY)
```
Table: AI_ChatBot_AuditLog
Model: services/models.py:191

Fields:
  entry_id              INTEGER PK autoincrement
  phone_number          VARCHAR(50)
  entry_type            VARCHAR(50)  — "incoming_message" | "outbound_trigger"
  input_message         TEXT         — what was received
  output_message        TEXT         — what was sent
  created_at            DATETIME
  CBM_ID                INTEGER      — FK-style to TriggeredUser (nullable for inbound)
  Email                 VARCHAR(50)
  Channel               VARCHAR
  ProcessingTimeSeconds FLOAT

NOTE: The CBM_ID field is nullable. This means some audit log entries cannot be
traced back to a specific trigger. This breaks the forensic reconstruction chain
for inbound messages that arrive without a known trigger context.
```

### Entity 6: EngagementEvent (APPEND-ONLY)
```
Table: AI_ChatBot_EngagementEvents
Model: services/models.py:228

Fields:
  id          INTEGER PK autoincrement
  user_id     INTEGER  nullable  — FK-style to TriggerData.UserID
  event_type  VARCHAR(100) NOT NULL  — "trigger", "incoming_message", "trigger_dispatched"
  channel     VARCHAR(50)   nullable
  message     TEXT          nullable
  agent_name  VARCHAR(100)  nullable
  trigger_id  INTEGER       nullable  — FK-style to TriggeredUser.CBM_ID
  thread_id   VARCHAR(255)  nullable  — for response matching
  created_at  DATETIME      nullable

GAP: No enum/constant for event_type values. Currently string literals scattered
across multiple files. Risk of typos creating unresolvable event types.

GAP vs. doctrine: event_driven_orchestration_model.md requires 10 mandatory
attributes including correlation_id, parent_event_id, governance_context,
payload_version, originating_environment. None of these fields exist.
```

### Entity 7: DeliveryLog (APPEND-ONLY)
```
Table: AI_ChatBot_DeliveryLog
Model: services/models.py:275

Fields:
  id            INTEGER PK autoincrement
  cbm_id        INTEGER  nullable  indexed  — FK-style to TriggeredUser
  user_id       INTEGER  nullable  — denormalized
  channel       VARCHAR(50)  nullable  — "sms" | "whatsapp" | "email"
  success       BOOLEAN  nullable
  error_message TEXT     nullable
  created_on    DATETIME nullable  default=utcnow
```

### Entity 8: StudentResponse (APPEND-ONLY)
```
Table: AI_ChatBot_StudentResponses
Model: services/models.py:427

Fields:
  id                  INTEGER PK autoincrement
  cbm_id              INTEGER NOT NULL  — links to originating trigger
  engagement_event_id INTEGER NOT NULL  — links to outbound EngagementEvent
  user_id             INTEGER NOT NULL
  response_channel    VARCHAR(50) NOT NULL
  match_method        VARCHAR(30) NOT NULL  — "thread_id"|"time_proximity"|"manual"
  confidence          FLOAT NOT NULL   — 0.0 to 1.0
  matched_at          DATETIME NOT NULL  — when match was created, NOT when student replied

NOTE: No DB UNIQUE constraint on engagement_event_id (models.py:440-443).
Application must enforce one response per engagement_event_id before every insert.
Risk: concurrent inbound messages could create duplicate StudentResponse rows.
```

### Entity 9: Directive (READ + WRITE)
```
Table: AI_ChatBot_Directives
Model: services/models.py:319

Fields:
  id         INTEGER PK autoincrement
  name       VARCHAR(100) UNIQUE NOT NULL
  content    TEXT
  version    INTEGER default=1
  created_at DATETIME
  updated_at DATETIME
```

### Entity 10: BehaviorFingerprint (WRITE)
```
Table: AI_ChatBot_BehaviorFingerprints
Model: services/models.py:349

Fields:
  id           INTEGER PK indexed
  entity_type  VARCHAR(50) NOT NULL  — "student"|"cohort"|"mentor"
  entity_id    VARCHAR(100) NOT NULL
  pattern_name VARCHAR(100) NOT NULL
  score        FLOAT NOT NULL  — 0.0 to 1.0 (matched/total thresholds)
  risk_level   VARCHAR(20) NOT NULL  — "low"|"medium"|"high"
  details_json TEXT  nullable
  created_at   DATETIME server_default=now()
```

### Entity 11: DiscoveredKPI (WRITE)
```
Table: AI_ChatBot_DiscoveredKPIs
Model: services/models.py:374

Fields:
  id             INTEGER PK autoincrement
  kpi_name       VARCHAR(100) NOT NULL
  source_pattern VARCHAR(100) NOT NULL
  entity_type    VARCHAR(50) NOT NULL
  formula        TEXT  nullable
  confidence     FLOAT NOT NULL
  sample_size    INTEGER NOT NULL
  discovered_at  DATETIME server_default=now()

WARNING: KPIDiscoveryAnalyzer (core/kpi_discovery/analyzer.py) always returns
a single hardcoded KPI: "avg_logins". No actual discovery occurs.
```

### Entity 12: GeneratedInsight (WRITE)
```
Table: AI_ChatBot_GeneratedInsights
Model: services/models.py:399

Fields:
  id                   INTEGER PK indexed
  title                VARCHAR(200) NOT NULL
  body                 TEXT NOT NULL
  insight_type         VARCHAR(50) NOT NULL  — "kpi"|"risk"
  entity_type          VARCHAR(50) NOT NULL
  entity_id            VARCHAR(100) NOT NULL
  source_kpis_json     TEXT  nullable
  source_patterns_json TEXT  nullable
  confidence           FLOAT NOT NULL
  created_at           DATETIME server_default=now()

NOTE: The "AI explanation" attached to insights (explanation, recommended_action)
is generated by keyword matching in skills/insight_explainer/skill.py — not LLM.
```

---

## ENTITY TO BUILD (GOVERNANCE GAP)

### Entity 13: ApprovalRequest (MISSING — P0)
```sql
-- Alembic migration 0010
CREATE TABLE AI_ChatBot_ApprovalRequests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type     VARCHAR(50)  NOT NULL,
    -- Values: 'trigger_dispatch_high_severity', 'schema_change', 'execution'
    scope_json      TEXT         NOT NULL,   -- JSON: what will happen
    rollback_json   TEXT,                    -- JSON: how to undo (nullable for now)
    status          VARCHAR(20)  NOT NULL DEFAULT 'pending',
    -- Values: 'pending', 'approved', 'denied', 'expired'
    requested_by    VARCHAR(100),
    approved_by     VARCHAR(100),
    denial_reason   TEXT,
    requested_at    DATETIME     NOT NULL,
    decided_at      DATETIME,
    cbm_id          INTEGER,  -- link to TriggeredUser if applicable
    expires_at      DATETIME  -- optional: auto-deny after N hours
);
```

---

## AGGREGATE RELATIONSHIPS

```
TriggerRule (CB_ID)
    ↓ evaluated against
TriggerData (UserID) — KPI values
    ↓ produces
TriggeredUser (CBM_ID) ← THE SPINE
    ↓ generates
ChatBotAuditLog (CBM_ID)
    ↓ generates
EngagementEvent (trigger_id = CBM_ID)
    ↓ generates
DeliveryLog (cbm_id = CBM_ID)
    ↓ generates
TriggeredUser.DeliverySucceeded (writeback)

Student reply arrives:
EngagementEvent (outbound) ← StudentResponse → TriggeredUser (CBM_ID)

Per-student state:
ConversationState (PhoneNumber) — one active conversation per contact

Intelligence overlay:
TriggerData → BehaviorFingerprint
             → DiscoveredKPI
             → GeneratedInsight

Directives: standalone, no foreign keys
ApprovalRequests [TO BUILD]: optional link to CBM_ID
```

---

## DATA INTEGRITY GAPS

| Gap | Risk | Fix |
|---|---|---|
| No UNIQUE constraint on `StudentResponse.engagement_event_id` | Concurrent inbound → duplicate responses | Application-level guard exists; add DB constraint in migration |
| `ChatBotAuditLog.CBM_ID` nullable | Inbound messages have no trigger link | Accept for now; add `student_session_id` concept later |
| `ConversationState` keyed by PhoneNumber | Number reassignment causes stale state | Add UserID as secondary key |
| `EngagementEvent.event_type` is a raw string | Typos create unresolvable types | Add `EventType` enum/constant module |
| `KPIDiscoveryAnalyzer` hardcoded | Discovery results are fake | Replace with real analysis logic |
| `StateJSON` unbounded | Memory growth for long conversations | Add max-turn trimming |
