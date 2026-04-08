"""Colaberry AI — FastAPI application boundary.

Thin HTTP layer only. No business logic, no DB, no external calls.
See directives/ai_mentor_message_contract.md for the full specification.
"""

import uuid
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware

from config.request_context import clear_request_id, set_request_id

from config.database import MSSQL_CONFIGURED, SessionLocal
from config.logging import configure_logging
from services.mentor_message_service import MentorMessageService
from services.student_status_fetcher import DbStudentStatusFetcher, StudentStatusFetcher, StubStudentStatusFetcher
from services.trigger_processing_service import DbTriggerProcessingService, TriggerProcessingService
from pydantic import BaseModel, field_validator
from api.routes.directives import router as directives_router
from api.routes.fingerprint import router as fingerprint_router
from api.routes.kpi import router as kpi_router
from api.routes.insight import router as insight_router
from config.auth import require_api_key

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="Colaberry AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    value = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    set_request_id(value)
    response = await call_next(request)
    clear_request_id()
    return response


app.include_router(directives_router, dependencies=[Depends(require_api_key)])
app.include_router(fingerprint_router, dependencies=[Depends(require_api_key)])
app.include_router(kpi_router,         dependencies=[Depends(require_api_key)])
app.include_router(insight_router,     dependencies=[Depends(require_api_key)])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class Channel(str, Enum):
    whatsapp = "whatsapp"
    sms = "sms"
    email = "email"
    voice = "voice"
    web = "web"


class TriggerProcessRequest(BaseModel):
    trigger_type: str
    student_id: str
    event_id: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("trigger_type", "student_id", "event_id")
    @classmethod
    def must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be non-empty")
        return v


class MentorMessageRequest(BaseModel):
    student_id: str
    channel: Channel
    message: str
    timestamp: Optional[str] = None
    thread_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("student_id", "message")
    @classmethod
    def must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be non-empty")
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class Received(BaseModel):
    student_id: str
    channel: str
    message: str


class StudentStatus(BaseModel):
    lifecycle_stage: str
    summary: str


class DeliveryConstraints(BaseModel):
    max_length: int


class Delivery(BaseModel):
    channel: str
    constraints: DeliveryConstraints


class ResponseMessage(BaseModel):
    text: str


class EngagementLog(BaseModel):
    logged: bool
    event_type: str


class TriggerProcessResponse(BaseModel):
    event_id: str
    accepted: bool
    actions_planned: list[str]
    notes: str


class MentorMessageResponse(BaseModel):
    request_id: str
    received: Received
    student_status: StudentStatus
    delivery: Delivery
    response_message: ResponseMessage
    engagement_log: EngagementLog


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

def get_student_status_fetcher() -> StudentStatusFetcher:
    if MSSQL_CONFIGURED:
        return DbStudentStatusFetcher()
    return StubStudentStatusFetcher()


@app.post("/ai/mentor/message", response_model=MentorMessageResponse, dependencies=[Depends(require_api_key)])
def post_mentor_message(
    body: MentorMessageRequest,
    x_request_id: Optional[str] = Header(None),
    status_fetcher: StudentStatusFetcher = Depends(get_student_status_fetcher),
) -> MentorMessageResponse:
    request_id = (
        x_request_id if x_request_id and x_request_id.strip() else str(uuid.uuid4())
    )

    result = MentorMessageService().handle(
        body=body, request_id=request_id, status_fetcher=status_fetcher,
    )
    return MentorMessageResponse(**result)


def get_trigger_processing_service():
    if SessionLocal is not None:
        return DbTriggerProcessingService()
    return TriggerProcessingService()


@app.post("/ai/trigger/process", response_model=TriggerProcessResponse, dependencies=[Depends(require_api_key)])
def post_trigger_process(
    body: TriggerProcessRequest,
    svc=Depends(get_trigger_processing_service),
) -> TriggerProcessResponse:
    result = svc.process(body.model_dump())
    return TriggerProcessResponse(**result)
