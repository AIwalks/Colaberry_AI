import logging
import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.database import get_db
from core.insight.service import InsightService
from services.ai_insight_service import generate_ai_insight
from api.schemas.insight import (
    AIInsightGenerateResponse,
    InsightGenerateRequest,
    InsightGenerateResponse,
)

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


@router.post("/generate/ai", response_model=AIInsightGenerateResponse)
def generate_ai_insights(
    body: InsightGenerateRequest,
    db: Session = Depends(get_db),
):
    logger.info(
        "generate_ai_insights called: entity_type=%r entity_id=%r",
        body.entity_type, body.entity_id,
    )

    if os.environ.get("ENABLE_AI_INSIGHTS", "").lower() != "true":
        logger.info("AI insights disabled — ENABLE_AI_INSIGHTS not set to 'true'")
        return {
            "ai_enabled": False,
            "entity_id": body.entity_id,
            "entity_type": body.entity_type,
            "analyzed_kpis": 0,
            "analyzed_fingerprints": 0,
            "insights": [],
            "message": (
                "AI insight generation is disabled. "
                "Set ENABLE_AI_INSIGHTS=true to enable."
            ),
        }

    service = InsightService()
    kpis = service.load_kpis(db, entity_id=body.entity_id, entity_type=body.entity_type)
    fingerprints = service.load_fingerprints(db, entity_id=body.entity_id, entity_type=body.entity_type)

    student_data = {
        "entity_id": body.entity_id,
        "entity_type": body.entity_type,
        "kpis": kpis,
        "fingerprints": fingerprints,
    }

    ai_result = generate_ai_insight(student_data)

    insight = {
        "id": 1,
        "title": f"AI Risk Assessment — {ai_result['risk_level'].upper()}",
        "body": ai_result["summary"],
        "insight_type": "ai",
        "entity_type": body.entity_type,
        "entity_id": body.entity_id,
        "confidence": ai_result["confidence"],
        "explanation": "; ".join(ai_result["explainability"]),
        "recommended_action": ai_result["recommended_action"],
        "risk_level": ai_result["risk_level"],
        "explainability": ai_result["explainability"],
    }

    return {
        "ai_enabled": True,
        "entity_id": body.entity_id,
        "entity_type": body.entity_type,
        "analyzed_kpis": len(kpis),
        "analyzed_fingerprints": len(fingerprints),
        "insights": [insight],
    }
