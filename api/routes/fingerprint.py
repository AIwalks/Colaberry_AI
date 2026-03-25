from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.database import get_db

from api.schemas.fingerprint import (
    FingerprintRequest,
    FingerprintResponse,
)

from core.fingerprint.patterns import BehaviorPattern
from core.fingerprint.service import FingerprintService


router = APIRouter(
    prefix="/fingerprints",
    tags=["fingerprints"],
)


@router.post(
    "/evaluate",
    response_model=FingerprintResponse,
)
def evaluate_fingerprint(
    request: FingerprintRequest,
    db: Session = Depends(get_db),
):

    pattern = BehaviorPattern(
        name=request.pattern_name,
        description="api",
        thresholds=request.thresholds,
    )

    service = FingerprintService()

    record = service.evaluate_and_store(
        db=db,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        pattern=pattern,
        metrics=request.metrics,
    )

    return FingerprintResponse(
        id=record.id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        pattern_name=record.pattern_name,
        score=record.score,
        risk_level=record.risk_level,
        details_json=record.details_json,
    )
