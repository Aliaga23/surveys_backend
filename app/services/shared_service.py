from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from uuid import UUID

from app.models.survey import CampanaEncuesta, EntregaEncuesta, PlantillaEncuesta, PreguntaEncuesta
from app.core.constants import ESTADO_RESPONDIDO

def get_entrega_con_plantilla(db: Session, entrega_id: UUID) -> Optional[EntregaEncuesta]:
    """Obtiene una entrega con todas sus relaciones cargadas"""
    return (
        db.query(EntregaEncuesta)
        .options(
            joinedload(EntregaEncuesta.campana)
            .joinedload(CampanaEncuesta.plantilla)
            .joinedload(PlantillaEncuesta.preguntas)
            .joinedload(PreguntaEncuesta.opciones),
            joinedload(EntregaEncuesta.destinatario)
        )
        .filter(EntregaEncuesta.id == entrega_id)
        .first()
    )

def mark_as_responded(db: Session, entrega_id: UUID) -> Optional[EntregaEncuesta]:
    """Marca una entrega como respondida"""
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if entrega:
        entrega.estado_id = ESTADO_RESPONDIDO
        entrega.respondido_en = datetime.now()
        db.commit()
        db.refresh(entrega)
    return entrega