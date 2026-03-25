from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.database import get_db
from core.insight.service import InsightService
from api.schemas.insight import InsightGenerateResponse


router = APIRouter(
    prefix="/insight",
    tags=["insight"],
)


@router.post("/generate", response_model=InsightGenerateResponse)
def generate_insights(
    db: Session = Depends(get_db),
):

    service = InsightService()

    result = service.generate_insights(db)

    return result
