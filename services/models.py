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

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Numeric, String, Text
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
