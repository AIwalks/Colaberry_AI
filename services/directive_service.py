from sqlalchemy.orm import Session
from typing import List, Optional

from services.models import Directive
from api.schemas.directives import DirectiveCreate, DirectiveUpdate


class DirectiveService:

    def get_all(self, db: Session) -> List[Directive]:
        return db.query(Directive).all()

    def get(self, db: Session, directive_id: int) -> Optional[Directive]:
        return db.query(Directive).filter(Directive.id == directive_id).first()

    def create(self, db: Session, data: DirectiveCreate) -> Directive:
        obj = Directive(
            name=data.name,
            content=data.content,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(
        self,
        db: Session,
        directive_id: int,
        data: DirectiveUpdate,
    ) -> Optional[Directive]:
        obj = db.query(Directive).filter(
            Directive.id == directive_id
        ).first()

        if not obj:
            return None

        if data.name is not None:
            obj.name = data.name

        if data.content is not None:
            obj.content = data.content

        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, directive_id: int) -> bool:
        obj = db.query(Directive).filter(
            Directive.id == directive_id
        ).first()

        if not obj:
            return False

        db.delete(obj)
        db.commit()
        return True
