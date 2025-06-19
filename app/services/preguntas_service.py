from typing import List, Optional
from sqlalchemy.orm import Session
from uuid import UUID
from sqlalchemy import desc

from app.models.survey import PreguntaEncuesta, OpcionEncuesta
from app.schemas.preguntas_schema import PreguntaCreate, PreguntaUpdate

def get_next_orden(db: Session, plantilla_id: UUID) -> int:
    """Obtiene el siguiente número de orden disponible para una plantilla"""
    ultimo = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.plantilla_id == plantilla_id)
        .order_by(desc(PreguntaEncuesta.orden))
        .first()
    )
    return (ultimo.orden + 1) if ultimo else 1

def create_pregunta(
    db: Session, 
    plantilla_id: UUID, 
    payload: PreguntaCreate
) -> PreguntaEncuesta:
    # Si no se especifica orden, usar el siguiente disponible
    if not payload.orden:
        payload.orden = get_next_orden(db, plantilla_id)
    
    # Crear la pregunta
    pregunta = PreguntaEncuesta(**payload.model_dump(), plantilla_id=plantilla_id)
    db.add(pregunta)
    db.commit()
    db.refresh(pregunta)
    return pregunta

def get_pregunta(db: Session, pregunta_id: UUID) -> Optional[PreguntaEncuesta]:
    return db.query(PreguntaEncuesta).filter(PreguntaEncuesta.id == pregunta_id).first()

def list_preguntas(db: Session, plantilla_id: UUID) -> List[PreguntaEncuesta]:
    return (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.plantilla_id == plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )

def update_pregunta(
    db: Session, 
    pregunta_id: UUID, 
    payload: PreguntaUpdate
) -> Optional[PreguntaEncuesta]:
    pregunta = get_pregunta(db, pregunta_id)
    if not pregunta:
        return None

    # Actualizar campos de la pregunta
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pregunta, field, value)
    
    db.commit()
    db.refresh(pregunta)
    return pregunta

def delete_pregunta(db: Session, pregunta_id: UUID) -> bool:
    pregunta = get_pregunta(db, pregunta_id)
    if not pregunta:
        return False
        
    # Reordenar las preguntas restantes
    preguntas_posteriores = (
        db.query(PreguntaEncuesta)
        .filter(
            PreguntaEncuesta.plantilla_id == pregunta.plantilla_id,
            PreguntaEncuesta.orden > pregunta.orden
        )
        .all()
    )
    
    for p in preguntas_posteriores:
        p.orden -= 1
    
    db.delete(pregunta)
    db.commit()
    return True