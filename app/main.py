"""Colaberry AI — FastAPI application boundary.

Thin HTTP layer only. No business logic, no DB, no external calls.
See directives/ai_mentor_message_contract.md for the full specification.
"""

import os
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware

from config.request_context import clear_request_id, set_request_id

from config.database import MSSQL_CONFIGURED, SENTINEL_LIVE, SENTINEL_SHADOW_MODE, SessionLocal
from config.logging import configure_logging
from services.mentor_message_service import MentorMessageService
from services.student_status_fetcher import DbStudentStatusFetcher, StudentStatusFetcher, StubStudentStatusFetcher
from services.trigger_processing_service import DbTriggerProcessingService, TriggerProcessingService
from pydantic import BaseModel, field_validator
from api.routes.directives import router as directives_router
from api.routes.fingerprint import router as fingerprint_router
from api.routes.kpi import router as kpi_router
from api.routes.insight import router as insight_router
from api.routes.sentinel import router as sentinel_router
from api.routes.twilio import router as twilio_router
from config.auth import require_api_key

import logging as _logging
_startup_logger = _logging.getLogger("colaberry.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    if not os.environ.get("API_KEY"):
        raise RuntimeError(
            "API_KEY environment variable is required but not set. "
            "Set API_KEY before starting the server."
        )

    # Sentinel shadow-mode startup validation
    if SENTINEL_SHADOW_MODE:
        _startup_logger.info(
            "SENTINEL_SHADOW_MODE=true — Sentinel live DB reads enabled: %s",
            SENTINEL_LIVE,
        )
        if SENTINEL_LIVE:
            try:
                from services.database_connection_validator import DatabaseConnectionValidator
                from config.database import engine as _engine
                result = DatabaseConnectionValidator(engine=_engine).run_full_validation()
                if result.passed:
                    _startup_logger.info(
                        "Sentinel DB validation passed — tables present: %s",
                        ", ".join(result.tables_present) or "none checked",
                    )
                else:
                    _startup_logger.warning(
                        "Sentinel DB validation issues (shadow-mode continues): %s",
                        "; ".join(result.errors),
                    )
            except Exception as exc:
                _startup_logger.warning(
                    "Sentinel DB validation raised unexpectedly — continuing in mock mode: %s", exc
                )
        else:
            _startup_logger.info(
                "Sentinel running in mock-data mode (MSSQL_CONFIGURED=%s)", MSSQL_CONFIGURED
            )
    else:
        _startup_logger.info("Sentinel shadow mode disabled (SENTINEL_SHADOW_MODE not set)")

    yield


app = FastAPI(title="Colaberry AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Api-Key", "X-Request-ID"],
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
app.include_router(sentinel_router,    dependencies=[Depends(require_api_key)])
app.include_router(twilio_router)  # auth handled per-request by validate_twilio_signature


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
