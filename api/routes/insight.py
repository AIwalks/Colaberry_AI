import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.database import get_db
from core.insight.service import InsightService
from api.schemas.insight import InsightGenerateRequest, InsightGenerateResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/insight",
    tags=["insight"],
)


@router.post("/generate", response_model=InsightGenerateResponse)
def generate_insights(
    body: InsightGenerateRequest,
    db: Session = Depends(get_db),
):
    logger.info("generate_insights called: entity_type=%r entity_id=%r", body.entity_type, body.entity_id)

    service = InsightService()

    result = service.generate_insights(db, entity_id=body.entity_id, entity_type=body.entity_type)

    return result
