from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from config.database import get_db
from services.directive_service import DirectiveService
from api.schemas.directives import (
    DirectiveCreate,
    DirectiveUpdate,
    DirectiveRead,
)

router = APIRouter(
    prefix="/directives",
    tags=["directives"],
)

service = DirectiveService()


@router.get("/", response_model=List[DirectiveRead])
def get_all(db: Session = Depends(get_db)):
    return service.get_all(db)


@router.get("/{directive_id}", response_model=DirectiveRead)
def get_one(directive_id: int, db: Session = Depends(get_db)):
    obj = service.get(db, directive_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Directive not found")
    return obj


@router.post("/", response_model=DirectiveRead)
def create(data: DirectiveCreate, db: Session = Depends(get_db)):
    return service.create(db, data)


@router.put("/{directive_id}", response_model=DirectiveRead)
def update(
    directive_id: int,
    data: DirectiveUpdate,
    db: Session = Depends(get_db),
):
    obj = service.update(db, directive_id, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Directive not found")
    return obj


@router.delete("/{directive_id}")
def delete(directive_id: int, db: Session = Depends(get_db)):
    ok = service.delete(db, directive_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Directive not found")
    return {"success": True}
