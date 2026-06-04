"""SQLAlchemy 2.0 ORM models for the Colaberry AI system.

These models describe tables that already exist in the SQL Server database.
Defining them here does NOT create or alter any tables.

Architecture note — Base
────────────────────────
Base is imported from config.database rather than redefined here with a second
declarative_base() call. One shared Base means one shared MetaData object,
which is required for Alembic autogenerate (alembic/env.py imports Base from
config.database to set target_metadata). A second Base would be invisible to
Alembic and break migration generation.

Usage pattern
─────────────
  from services.models import TriggerData, TriggerRule, TriggeredUser
  from services.models import ConversationState, ChatBotAuditLog

Read-only models:   TriggerData, TriggerRule
Read + write:       TriggeredUser, ConversationState
Write-only:         ChatBotAuditLog, EngagementEvent
"""

import enum
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, func, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from config.database import Base  # shared Base — do not redefine here


# ---------------------------------------------------------------------------
# 1. TriggerData
# ---------------------------------------------------------------------------

class TriggerData(Base):
    """Maps to AI_ChatBot_TriggerData (read-only).

    Primary source for student lifecycle status, identity, and channel routing.
    Used by:
      - StudentStatusFetcher  → ActiveStatus, StatusI, StatusII
      - MentorMessageService  → FirstName, LastName, Email, PhoneNumber
      - TriggerEvaluator      → KPI columns below (read via getattr)
    """

    __tablename__ = "AI_ChatBot_TriggerData"

    UserID: Mapped[int] = mapped_column(Integer, primary_key=True)
    UserName: Mapped[str] = mapped_column(String(100))
    FirstName: Mapped[str] = mapped_column(String(50))
    LastName: Mapped[str] = mapped_column(String(50))
    Email: Mapped[Optional[str]] = mapped_column(String(256))
    PhoneNumber: Mapped[Optional[str]] = mapped_column(String(20))
    ActiveStatus: Mapped[Optional[str]] = mapped_column(String(10))
    StatusI: Mapped[Optional[str]] = mapped_column(String(10))
    StatusII: Mapped[Optional[str]] = mapped_column(String(4000))

    # KPI columns — read by TriggerEvaluator via getattr(student, rule.KPI)
    Past10DaysLogon:          Mapped[Optional[int]]   = mapped_column(Integer,  nullable=True)
    LastActivityDays:         Mapped[Optional[int]]   = mapped_column(Integer,  nullable=True)
    LastLoginDays:            Mapped[Optional[int]]   = mapped_column(Integer,  nullable=True)
    DaysInStatus:             Mapped[Optional[int]]   = mapped_column(Integer,  nullable=True)
    HWsBehind:                Mapped[Optional[int]]   = mapped_column(Integer,  nullable=True)
    AttendancePercentage:     Mapped[Optional[float]] = mapped_column(Float,    nullable=True)
    AvgHWScore:               Mapped[Optional[float]] = mapped_column(Float,    nullable=True)
    AvgEffRating:             Mapped[Optional[float]] = mapped_column(Float,    nullable=True)
    NoOfAssignmentsSubmitted: Mapped[Optional[int]]   = mapped_column(Integer,  nullable=True)
    TotalNoOfAssignments:     Mapped[Optional[int]]   = mapped_column(Integer,  nullable=True)
    Total_Payments:           Mapped[Optional[float]] = mapped_column(Float,    nullable=True)
    PaymentBalance:           Mapped[Optional[int]]   = mapped_column(Integer,  nullable=True)
    IsClassActive:            Mapped[Optional[int]]   = mapped_column(Integer,  nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TriggerData UserID={self.UserID} "
            f"UserName={self.UserName!r} "
            f"ActiveStatus={self.ActiveStatus!r}>"
        )


# ---------------------------------------------------------------------------
# 2. TriggerRule
# ---------------------------------------------------------------------------

class TriggerRule(Base):
    """Maps to AI_ChatBot_TriggerRules (read-only).

    Defines which triggers fire for which KPI thresholds and at what severity.
    Used by TriggerProcessingService to replace the hardcoded _TRIGGER_MAP dict.
    AgentID links a rule to the Agent_Agents table for agent-based dispatch.
    """

    __tablename__ = "AI_ChatBot_TriggerRules"

    CB_ID: Mapped[int] = mapped_column(Integer, primary_key=True)
    TriggerType: Mapped[Optional[str]] = mapped_column(String)
    KPI: Mapped[Optional[str]] = mapped_column(String)
    Severity: Mapped[Optional[int]] = mapped_column(Integer)
    TriggerLow: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    TriggerHigh: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    ChatGPTPromptLowTrigger: Mapped[Optional[str]] = mapped_column(Text)
    ChatGPTPromptHighTrigger: Mapped[Optional[str]] = mapped_column(Text)
    AgentID: Mapped[Optional[int]] = mapped_column(Integer)

    def __repr__(self) -> str:
        return (
            f"<TriggerRule CB_ID={self.CB_ID} "
            f"TriggerType={self.TriggerType!r} "
            f"KPI={self.KPI!r} Severity={self.Severity}>"
        )


# ---------------------------------------------------------------------------
# 3. TriggeredUser
# ---------------------------------------------------------------------------

class TriggeredUser(Base):
    """Maps to AI_ChatBot_TriggeredUsers (read + write).

    One row per fired trigger event per student.
    CBM_ID is the central join key referenced by ChatBotAuditLog and
    Agent_CommunicationLogs — it links a communication back to the trigger
    event that originated it.

    Written to by TriggerProcessingService when a trigger is accepted.
    CB_ID is a foreign key to TriggerRule.CB_ID.
    """

    __tablename__ = "AI_ChatBot_TriggeredUsers"

    CBM_ID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    CB_ID: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("AI_ChatBot_TriggerRules.CB_ID")
    )
    UserID: Mapped[Optional[int]] = mapped_column(Integer)
    TriggerType: Mapped[Optional[str]] = mapped_column(String)
    TriggerLevel: Mapped[Optional[str]] = mapped_column(String)
    KPI: Mapped[Optional[str]] = mapped_column(String)
    Severity: Mapped[Optional[int]] = mapped_column(Integer)
    InsertDate: Mapped[Optional[datetime]] = mapped_column(DateTime)
    Completed: Mapped[Optional[int]] = mapped_column(Integer)
    CompletedDate: Mapped[Optional[datetime]] = mapped_column(DateTime)
    AgentID: Mapped[Optional[int]] = mapped_column(Integer)
    DeliverySucceeded: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TriggeredUser CBM_ID={self.CBM_ID} "
            f"UserID={self.UserID} "
            f"TriggerType={self.TriggerType!r} "
            f"Completed={self.Completed}>"
        )


# ---------------------------------------------------------------------------
# 4. ConversationState
# ---------------------------------------------------------------------------

class ConversationState(Base):
    """Maps to AI_ChatBot_ConversationState (read + write).

    One row per active student conversation, keyed by PhoneNumber.
    StateJSON holds the full conversation context as a serialized JSON blob.
    Read and written by MentorMessageService to maintain continuity
    across multi-turn interactions.
    LastUpdated should be set on every write.
    """

    __tablename__ = "AI_ChatBot_ConversationState"

    PhoneNumber: Mapped[str] = mapped_column(String(50), primary_key=True)
    Email: Mapped[Optional[str]] = mapped_column(String(255))
    Channel: Mapped[Optional[str]] = mapped_column(String(50))
    StateJSON: Mapped[Optional[str]] = mapped_column(Text)
    LastUpdated: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return (
            f"<ConversationState PhoneNumber={self.PhoneNumber!r} "
            f"Channel={self.Channel!r} "
            f"LastUpdated={self.LastUpdated}>"
        )


# ---------------------------------------------------------------------------
# 5. ChatBotAuditLog
# ---------------------------------------------------------------------------

class ChatBotAuditLog(Base):
    """Maps to AI_ChatBot_AuditLog (write-only).

    Append-only log of every inbound message and outbound response.
    This is the real implementation of the engagement_log stub currently
    returned as {"logged": true, "event_type": "incoming_message"}.

    CBM_ID links each entry back to the TriggeredUser record that prompted
    the interaction. Set CBM_ID=None for unsolicited inbound messages.
    entry_id is autoincrement — never set it manually.
    """

    __tablename__ = "AI_ChatBot_AuditLog"

    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(50))
    entry_type: Mapped[Optional[str]] = mapped_column(String(50))
    input_message: Mapped[Optional[str]] = mapped_column(Text)
    output_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    CBM_ID: Mapped[Optional[int]] = mapped_column(Integer)
    Email: Mapped[Optional[str]] = mapped_column(String(50))
    Channel: Mapped[Optional[str]] = mapped_column(String)
    ProcessingTimeSeconds: Mapped[Optional[float]] = mapped_column(Float)

    def __repr__(self) -> str:
        return (
            f"<ChatBotAuditLog entry_id={self.entry_id} "
            f"entry_type={self.entry_type!r} "
            f"Channel={self.Channel!r}>"
        )


# ---------------------------------------------------------------------------
# 6. EngagementEvent
# ---------------------------------------------------------------------------

class EngagementEvent(Base):
    """Maps to AI_ChatBot_EngagementEvents (write-only, append-only).

    Purpose-built engagement tracking table.  One row per discrete engagement
    event: a trigger firing, a message sent, a nudge delivered, etc.

    Fields
    ------
    id          — autoincrement PK, returned to the caller after insert.
    user_id     — FK-style reference to AI_ChatBot_TriggerData.UserID; nullable
                  for system-level or anonymous events.
    event_type  — required classifier, e.g. "nudge_sent", "trigger_fired".
    channel     — delivery channel: "whatsapp", "sms", "email", "web", etc.
    message     — human-readable description or the actual message text.
    agent_name  — name of the agent that produced the event, e.g. "MentorAgent".
    trigger_id  — FK-style reference to AI_ChatBot_TriggeredUsers.CBM_ID;
                  None for events that were not triggered by a rule evaluation.
    created_at  — set automatically to UTC now on insert; never updated.

    This table is additive only — rows are never modified or deleted.
    """

    __tablename__ = "AI_ChatBot_EngagementEvents"

    id:         Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:    Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str]           = mapped_column(String(100), nullable=False)
    channel:    Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    message:    Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    trigger_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EngagementEvent id={self.id} "
            f"event_type={self.event_type!r} "
            f"user_id={self.user_id} "
            f"channel={self.channel!r}>"
        )


# ---------------------------------------------------------------------------
# 7. DeliveryLog
# ---------------------------------------------------------------------------

class DeliveryLog(Base):
    """Maps to AI_ChatBot_DeliveryLog (write-only, append-only).

    One row per delivery attempt made by OutboundDeliveryService.
    Records whether the send succeeded or failed, which channel was used,
    and the error message if applicable.

    Fields
    ------
    id            — autoincrement PK, never set manually.
    cbm_id        — reference to AI_ChatBot_TriggeredUsers.CBM_ID; indexed
                    for fast lookup by trigger event. No FK constraint.
    user_id       — denormalized copy from TriggeredUser; avoids a join on reads.
    channel       — delivery channel used: "sms", "whatsapp", "email".
    success       — True if delivery was accepted; False on error.
    error_message — exception message on failure; None on success.
    created_on    — UTC timestamp set at write time; never updated.

    This table is additive only — rows are never modified or deleted.
    """

    __tablename__ = "AI_ChatBot_DeliveryLog"

    id:            Mapped[int]            = mapped_column(Integer,     primary_key=True, autoincrement=True)
    cbm_id:        Mapped[Optional[int]]  = mapped_column(Integer,     nullable=True,    index=True)
    user_id:       Mapped[Optional[int]]  = mapped_column(Integer,     nullable=True)
    channel:       Mapped[Optional[str]]  = mapped_column(String(50),  nullable=True)
    success:       Mapped[Optional[bool]] = mapped_column(Boolean,     nullable=True)
    error_message: Mapped[Optional[str]]  = mapped_column(Text,        nullable=True)
    created_on:    Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<DeliveryLog id={self.id} "
            f"cbm_id={self.cbm_id} "
            f"channel={self.channel!r} "
            f"success={self.success}>"
        )


# ---------------------------------------------------------------------------
# 8. Directive
# ---------------------------------------------------------------------------

class Directive(Base):
    """
    Maps to AI_ChatBot_Directives (read + write).

    Stores versioned directive definitions managed via CRUD API.
    One row per directive; name is unique.
    """

    __tablename__ = "AI_ChatBot_Directives"

    id:         Mapped[int]           = mapped_column(Integer,      primary_key=True, autoincrement=True)
    name:       Mapped[str]           = mapped_column(String(100),  nullable=False,   unique=True)
    content:    Mapped[Optional[str]] = mapped_column(Text,         nullable=True)
    version:    Mapped[Optional[int]] = mapped_column(Integer,      nullable=True,    default=1)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Directive id={self.id} "
            f"name={self.name!r} "
            f"version={self.version}>"
        )


# ---------------------------------------------------------------------------
# 9. BehaviorFingerprint
# ---------------------------------------------------------------------------

class BehaviorFingerprint(Base):
    __tablename__ = "AI_ChatBot_BehaviorFingerprints"

    id            = Column(Integer,      primary_key=True, index=True)
    entity_type   = Column(String(50),   nullable=False)
    entity_id     = Column(String(100),  nullable=False)
    pattern_name  = Column(String(100),  nullable=False)
    score         = Column(Float,        nullable=False)
    risk_level    = Column(String(20),   nullable=False)
    details_json  = Column(Text,         nullable=True)
    created_at    = Column(DateTime,     server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<BehaviorFingerprint id={self.id} "
            f"entity_type={self.entity_type!r} "
            f"entity_id={self.entity_id!r} "
            f"pattern_name={self.pattern_name!r} "
            f"risk_level={self.risk_level!r}>"
        )


# ---------------------------------------------------------------------------
# 10. DiscoveredKPI
# ---------------------------------------------------------------------------

class DiscoveredKPI(Base):
    __tablename__ = "AI_ChatBot_DiscoveredKPIs"

    id             = Column(Integer,      primary_key=True, autoincrement=True)
    kpi_name       = Column(String(100),  nullable=False)
    source_pattern = Column(String(100),  nullable=False)
    entity_type    = Column(String(50),   nullable=False)
    formula        = Column(Text,         nullable=True)
    confidence     = Column(Float,        nullable=False)
    sample_size    = Column(Integer,      nullable=False)
    discovered_at  = Column(DateTime,     server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<DiscoveredKPI id={self.id} "
            f"kpi_name={self.kpi_name!r} "
            f"entity_type={self.entity_type!r} "
            f"confidence={self.confidence}>"
        )


# ---------------------------------------------------------------------------
# 11. GeneratedInsight
# ---------------------------------------------------------------------------

class GeneratedInsight(Base):
    __tablename__ = "AI_ChatBot_GeneratedInsights"

    id                   = Column(Integer,      primary_key=True, index=True)
    title                = Column(String(200),  nullable=False)
    body                 = Column(Text,         nullable=False)
    insight_type         = Column(String(50),   nullable=False)
    entity_type          = Column(String(50),   nullable=False)
    entity_id            = Column(String(100),  nullable=False)
    source_kpis_json     = Column(Text,         nullable=True)
    source_patterns_json = Column(Text,         nullable=True)
    confidence           = Column(Float,        nullable=False)
    created_at           = Column(DateTime,     server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<GeneratedInsight id={self.id} "
            f"title={self.title!r} "
            f"insight_type={self.insight_type!r} "
            f"entity_type={self.entity_type!r} "
            f"confidence={self.confidence}>"
        )


# ---------------------------------------------------------------------------
# Enums for AIInterpretation
# ---------------------------------------------------------------------------

class InterpretationDimension(str, enum.Enum):
    engagement                   = "engagement"
    assignment_performance       = "assignment_performance"
    learning_effectiveness       = "learning_effectiveness"
    retention_risk               = "retention_risk"
    communication_responsiveness = "communication_responsiveness"
    intervention_effectiveness   = "intervention_effectiveness"


class InterpretationRiskLevel(str, enum.Enum):
    low      = "low"
    medium   = "medium"
    high     = "high"
    critical = "critical"
    unknown  = "unknown"


class InterpretationGeneratedBy(str, enum.Enum):
    claude               = "claude"
    deterministic_engine = "deterministic_engine"
    fallback             = "fallback"


def _stale_after_default() -> datetime:
    """Column default: created_at + 14 days. Called at INSERT time by SQLAlchemy."""
    return datetime.utcnow() + timedelta(days=14)


# ---------------------------------------------------------------------------
# 12. AIInterpretation
# ---------------------------------------------------------------------------

class AIInterpretation(Base):
    """Maps to AI_ChatBot_AIInterpretations (write-only, append-only).

    Durable, versioned, auditable AI-generated student state evaluations.

    Invalidation over deletion
    ──────────────────────────
    Historical interpretations are never deleted. When new data supersedes an
    existing interpretation, the old record is marked inactive (is_active=False,
    invalidated_at set, invalidation_reason recorded) and a new record is inserted.
    This preserves the causal chain: any mentor action or governance decision
    referencing an interpretation_id remains traceable indefinitely.

    source_metrics_hash
    ───────────────────
    SHA-256 hex of the input KPI + fingerprint payload. Query pattern:
      WHERE entity_id = ? AND source_metrics_hash = ?
        AND is_active = 1 AND stale_after > NOW()
    If a row matches, return the cached interpretation — no Claude call needed.

    stale_after
    ───────────
    Defaults to INSERT time + 14 days via _stale_after_default(). Interpretations
    past this date are treated as unactionable by the governance layer even if
    is_active = True.

    Future integration points
    ─────────────────────────
    - MaterialChangeEngine: compares consecutive interpretations for significant delta
    - GovernanceApprovalService: routes high-risk rows to ApprovalRequests table
    - EngagementEvents: INSIGHT_GENERATED event keyed by entity_id
    """

    __tablename__ = "AI_ChatBot_AIInterpretations"

    id                     = Column(Integer,     primary_key=True, autoincrement=True)
    created_at             = Column(DateTime,    nullable=False,  default=datetime.utcnow)
    updated_at             = Column(DateTime,    nullable=False,  default=datetime.utcnow, onupdate=datetime.utcnow)
    invalidated_at         = Column(DateTime,    nullable=True)

    entity_id              = Column(String(100), nullable=False,  index=True)
    entity_type            = Column(String(50),  nullable=False,  index=True)

    dimension              = Column(String(50),  nullable=False)
    interpretation_version = Column(Integer,     nullable=False,  default=1)

    confidence             = Column(Float,       nullable=False)
    risk_level             = Column(String(20),  nullable=False)

    summary                = Column(Text,        nullable=False)
    recommended_action     = Column(Text,        nullable=True)

    explainability_json    = Column(Text,        nullable=True)   # JSON-serialized list[str]
    source_metrics_hash    = Column(String(64),  nullable=True,   index=True)
    source_snapshot_json   = Column(Text,        nullable=True)   # JSON-serialized dict

    generated_by           = Column(String(30),  nullable=False)
    model_name             = Column(String(100), nullable=True)

    stale_after            = Column(DateTime,    nullable=True,   default=_stale_after_default)
    is_active              = Column(Boolean,     nullable=False,  default=True)
    invalidation_reason    = Column(Text,        nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AIInterpretation id={self.id} "
            f"entity_id={self.entity_id!r} "
            f"dimension={self.dimension!r} "
            f"risk_level={self.risk_level!r} "
            f"confidence={self.confidence} "
            f"is_active={self.is_active}>"
        )


# ---------------------------------------------------------------------------
# Enums for GovernanceReview
# ---------------------------------------------------------------------------

class GovernanceReviewStatus(str, enum.Enum):
    pending  = "pending"
    approved = "approved"
    rejected = "rejected"
    deferred = "deferred"


# ---------------------------------------------------------------------------
# 13. GovernanceReview
# ---------------------------------------------------------------------------

class GovernanceReview(Base):
    """Maps to AI_ChatBot_GovernanceReviews (write + update, never delete).

    Human-governed review queue for AI-generated interpretations.
    Every new AIInterpretation automatically creates a GovernanceReview(status="pending").
    No downstream automation may execute until status="approved".

    Lifecycle
    ─────────
    pending  → approved  : reviewer confirms risk level is actionable
    pending  → rejected  : reviewer disputes interpretation (review_notes required)
    pending  → deferred  : reviewer requests more data (governance_reason required)
    approved → deferred  : rare edge case — escalation after initial approval

    Historical preservation
    ───────────────────────
    Review records are never deleted. is_active=False is reserved for future
    supersession logic (e.g., a new review row replaces this one). In V1 it is
    always True.

    audit_snapshot_json
    ───────────────────
    JSON capture of the interpretation state and governance context at the moment
    the review was created. Immutable after creation. Provides a self-contained
    audit record that remains valid even if the referenced interpretation is later
    invalidated or updated.
    """

    __tablename__ = "AI_ChatBot_GovernanceReviews"

    id                  = Column(Integer,     primary_key=True, autoincrement=True)
    created_at          = Column(DateTime,    nullable=False,   default=datetime.utcnow)
    updated_at          = Column(DateTime,    nullable=False,   default=datetime.utcnow,
                                              onupdate=datetime.utcnow)

    interpretation_id   = Column(Integer,     nullable=False,   index=True)
    entity_id           = Column(String(100), nullable=False,   index=True)
    entity_type         = Column(String(50),  nullable=False)

    status              = Column(String(20),  nullable=False,   default="pending")

    reviewed_by         = Column(String(200), nullable=True)
    reviewed_at         = Column(DateTime,    nullable=True)
    review_notes        = Column(Text,        nullable=True)

    governance_reason   = Column(Text,        nullable=False)
    risk_level          = Column(String(20),  nullable=False)
    confidence          = Column(Float,       nullable=False)

    audit_snapshot_json = Column(Text,        nullable=True)    # JSON-serialized dict, immutable
    is_active           = Column(Boolean,     nullable=False,   default=True)

    def __repr__(self) -> str:
        return (
            f"<GovernanceReview id={self.id} "
            f"interpretation_id={self.interpretation_id} "
            f"entity_id={self.entity_id!r} "
            f"status={self.status!r} "
            f"risk_level={self.risk_level!r}>"
        )


# ---------------------------------------------------------------------------
# 14. InterventionOutcome
# ---------------------------------------------------------------------------

class InterventionOutcome(Base):
    """Maps to AI_ChatBot_InterventionOutcomes (write + update, never delete).

    One row per fired trigger. Records the before-state at enrollment time,
    the after-state when the evaluation window closes, and the computed
    outcome label.  Primary input for the Outcome Learning system.

    Lifecycle
    ─────────
    pending      → improved     : after_last_activity_days < before by >= minimum_delta_days
    pending      → not_improved : delivery succeeded but no measurable activity recovery
    pending      → inconclusive : delivery gate failed, before-state unavailable, student
                                  was already healthy, or after-state could not be captured

    Enrollment
    ──────────
    Created by InterventionOutcomeService.enroll() immediately after
    MentorMessageService writes DeliverySucceeded to TriggeredUsers.
    The UNIQUE constraint on cbm_id enforces one evaluation per trigger —
    duplicate enroll() calls are safe no-ops.

    Evaluation
    ──────────
    Scored by InterventionOutcomeService.evaluate_ready_outcomes() when
    window_end <= utcnow() and outcome = 'pending'.  The composite index on
    (outcome, window_end) makes this query efficient.

    before_snapshot_source
    ──────────────────────
    'interpretation' — last_activity_days read from AIInterpretation.source_snapshot_json.
                       Immutable frozen snapshot; preferred source.
    'trigger_data'   — read live from TriggerData.LastActivityDays at enrollment time.
                       Valid fallback when no interpretation exists for the student.
    'unavailable'    — neither source accessible; outcome will be inconclusive.

    entity_id / user_id type mismatch
    ──────────────────────────────────
    AIInterpretation.entity_id is String(100); TriggeredUsers.UserID is Integer.
    The enrollment lookup uses entity_id = str(user_id) at the application layer.
    No database-level FK is defined here — consistent with the FK-style reference
    pattern used by DeliveryLog.cbm_id and GovernanceReview.interpretation_id.
    """

    __tablename__ = "AI_ChatBot_InterventionOutcomes"

    __table_args__ = (
        # Composite index — the scheduler query:
        #   WHERE outcome = 'pending' AND window_end <= NOW()
        Index("ix_intervention_outcomes_outcome_window_end", "outcome", "window_end"),
    )

    id                        = Column(Integer,     primary_key=True, autoincrement=True)
    created_at                = Column(DateTime,    nullable=False,  default=datetime.utcnow)
    updated_at                = Column(DateTime,    nullable=False,  default=datetime.utcnow,
                                       onupdate=datetime.utcnow)

    # --- Intervention identity -------------------------------------------------
    cbm_id                    = Column(Integer,     nullable=False,  unique=True)
    # FK-style ref to AI_ChatBot_TriggeredUsers.CBM_ID; unique = one eval per trigger.

    user_id                   = Column(Integer,     nullable=True,   index=True)
    # Denormalized from TriggeredUsers.UserID; nullable because UserID is Optional on
    # TriggeredUsers — rows with UserID=NULL must still be enrolled.

    interpretation_id         = Column(Integer,     nullable=True,   index=True)
    # FK-style ref to AI_ChatBot_AIInterpretations.id active at window_start.
    # NULL when no interpretation existed for the student at trigger time.

    # --- Evaluation window ----------------------------------------------------
    window_start              = Column(DateTime,    nullable=False)
    # Copied from TriggeredUsers.InsertDate at enrollment time.

    window_end                = Column(DateTime,    nullable=False)
    # = window_start + evaluation_window_days days.

    evaluation_window_days    = Column(Integer,     nullable=False,  default=14)
    # Stored per-record so the window used is self-documenting and can vary
    # by trigger type or experiment group in future sprints.

    # --- Delivery gate --------------------------------------------------------
    delivery_gate_passed      = Column(Boolean,     nullable=False,  default=False)
    # True only when TriggeredUsers.DeliverySucceeded = True.
    # Records where this is False are always inconclusive — the intervention
    # never reached the student so no outcome can be attributed to it.

    # --- Before-state (captured at enrollment) --------------------------------
    before_last_activity_days = Column(Integer,     nullable=True)
    before_risk_level         = Column(String(20),  nullable=True)
    before_snapshot_source    = Column(String(30),  nullable=False,  default="unavailable")
    # See docstring for valid values: 'interpretation' | 'trigger_data' | 'unavailable'

    # --- After-state (populated by evaluation job) ----------------------------
    after_last_activity_days  = Column(Integer,     nullable=True)
    after_risk_level          = Column(String(20),  nullable=True)
    after_captured_at         = Column(DateTime,    nullable=True)

    # --- Outcome --------------------------------------------------------------
    outcome                   = Column(String(20),  nullable=False,  default="pending")
    # 'pending' | 'improved' | 'not_improved' | 'inconclusive'

    outcome_reason            = Column(String(300), nullable=True)
    # Machine-written plain-English explanation of the classification decision.

    eligible_for_learning     = Column(Boolean,     nullable=True,   index=True)
    # True  → improved or not_improved; record is a labeled training example.
    # False → inconclusive; excluded from learning aggregates.
    # NULL  → pending; not yet determined.

    evaluated_at              = Column(DateTime,    nullable=True)

    def __repr__(self) -> str:
        return (
            f"<InterventionOutcome id={self.id} "
            f"cbm_id={self.cbm_id} "
            f"user_id={self.user_id} "
            f"outcome={self.outcome!r} "
            f"eligible_for_learning={self.eligible_for_learning}>"
        )


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

class Recommendation(Base):
    """Maps to AI_ChatBot_Recommendations (write-only, append-only).

    One row per recommendation generated for a triggered student.  Records the
    exact recommendation surfaced to the mentor alongside the frozen student
    context that produced it.

    Invalidation over deletion
    ──────────────────────────
    Recommendations are never deleted.  When a newer recommendation supersedes
    an existing one for the same (cbm_id, recommendation_key), the old row is
    marked inactive (is_active=False, invalidated_at set, invalidation_reason
    recorded) and a new row is inserted.

    recommendation_key vs recommendation_type
    ──────────────────────────────────────────
    recommendation_type  — broad action category for display ('reach_out',
                           'escalate', 'monitor', 'academic_support').
    recommendation_key   — granular learning identifier ('attendance_outreach',
                           'homework_outreach', 'inactivity_outreach',
                           'high_risk_escalation').  This is the primary key
                           for all success-rate calculations.

    recommendation_context_json
    ───────────────────────────
    NOT NULL.  JSON string (serialized by the service layer) capturing the
    exact student state at generation time — risk_level, KPI values, dimension,
    interpretation summary.  Preserves explainability even if interpretations
    evolve later.  Supply '{}' if no context is available; never NULL.

    No ORM relationships are declared.  Joins to AIInterpretation and
    InterventionOutcome are performed via explicit queries in the service layer,
    consistent with the FK-style reference pattern used throughout this file.
    """

    __tablename__ = "AI_ChatBot_Recommendations"

    id                          = Column(Integer,     primary_key=True, autoincrement=True)
    created_at                  = Column(DateTime,    nullable=False,  default=datetime.utcnow)
    updated_at                  = Column(DateTime,    nullable=False,  default=datetime.utcnow,
                                         onupdate=datetime.utcnow)

    # --- Trigger + interpretation linkage ------------------------------------
    cbm_id                      = Column(Integer,     nullable=False,  index=True)
    # FK-style ref to AI_ChatBot_TriggeredUsers.CBM_ID.

    interpretation_id           = Column(Integer,     nullable=True)
    # FK-style ref to AI_ChatBot_AIInterpretations.id active at generation time.
    # NULL when no interpretation existed for the student.

    # --- Student identity ----------------------------------------------------
    entity_id                   = Column(String(100), nullable=False,  index=True)

    # --- Recommendation classification ---------------------------------------
    recommendation_type         = Column(String(50),  nullable=False)
    # Broad action category — display only; not used for learning calculations.

    recommendation_key          = Column(String(100), nullable=False,  index=True)
    # Granular learning identifier — primary key for all success-rate aggregations.

    recommendation_text         = Column(Text,        nullable=False)
    # Full recommendation text as shown to the mentor.

    # --- Context at generation time ------------------------------------------
    dimension                   = Column(String(50),  nullable=False,  index=True)
    risk_level                  = Column(String(20),  nullable=False)
    confidence                  = Column(Float,       nullable=False)

    recommendation_context_json = Column(Text,        nullable=False)
    # JSON-serialized dict of the student state at generation time.
    # Callers serialize with json.dumps; consumers deserialize with json.loads.
    # NOT NULL — supply '{}' if no context is available.

    # --- Provenance ----------------------------------------------------------
    generated_by                = Column(String(50),  nullable=False)
    model_name                  = Column(String(100), nullable=True)

    # --- Lifecycle -----------------------------------------------------------
    is_active                   = Column(Boolean,     nullable=False,  default=True)
    # True on insert.  Set to False when a newer recommendation supersedes this one.

    invalidated_at              = Column(DateTime,    nullable=True)
    invalidation_reason         = Column(Text,        nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Recommendation id={self.id} "
            f"cbm_id={self.cbm_id} "
            f"recommendation_key={self.recommendation_key!r} "
            f"dimension={self.dimension!r} "
            f"is_active={self.is_active}>"
        )
