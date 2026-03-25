from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from config.database import get_db

from core.kpi_discovery.service import KPIDiscoveryService


router = APIRouter(
    prefix="/kpi",
    tags=["kpi"],
)


@router.post("/discover")
def discover_kpis(
    db: Session = Depends(get_db),
):

    service = KPIDiscoveryService()

    result = service.discover_kpis(db)

    return {
        "kpis_found": len(result.kpis),
        "kpis": [k.kpi_name for k in result.kpis.values()],
    }
