from typing import List, Optional
from sqlalchemy.orm import Session
from uuid import UUID

from app.models.survey import OpcionEncuesta
from app.schemas.preguntas_schema import OpcionCreate

def create_opcion(
    db: Session, 
    pregunta_id: UUID, 
    payload: OpcionCreate
) -> OpcionEncuesta:
    opcion = OpcionEncuesta(**payload.model_dump(), pregunta_id=pregunta_id)
    db.add(opcion)
    db.commit()
    db.refresh(opcion)
    return opcion

def get_opcion(db: Session, opcion_id: UUID) -> Optional[OpcionEncuesta]:
    return db.query(OpcionEncuesta).filter(OpcionEncuesta.id == opcion_id).first()

def list_opciones(db: Session, pregunta_id: UUID) -> List[OpcionEncuesta]:
    return db.query(OpcionEncuesta).filter(
        OpcionEncuesta.pregunta_id == pregunta_id
    ).all()

def update_opcion(
    db: Session, 
    opcion_id: UUID, 
    payload: OpcionCreate
) -> Optional[OpcionEncuesta]:
    opcion = get_opcion(db, opcion_id)
    if not opcion:
        return None
    
    for field, value in payload.model_dump().items():
        setattr(opcion, field, value)
    
    db.commit()
    db.refresh(opcion)
    return opcion

def delete_opcion(db: Session, opcion_id: UUID) -> bool:
    opcion = get_opcion(db, opcion_id)
    if not opcion:
        return False
    db.delete(opcion)
    db.commit()
    return True