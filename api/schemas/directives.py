from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DirectiveBase(BaseModel):
    name: str
    content: Optional[str] = None


class DirectiveCreate(DirectiveBase):
    pass


class DirectiveUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None


class DirectiveRead(DirectiveBase):
    id: int
    version: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
