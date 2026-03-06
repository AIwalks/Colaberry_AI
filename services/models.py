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
Write-only:         ChatBotAuditLog
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
