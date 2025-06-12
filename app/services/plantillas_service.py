from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from app.models.survey import PlantillaEncuesta, PreguntaEncuesta
from app.schemas.plantillas_schema import PlantillaCreate, PlantillaUpdate

def create_plantilla(db: Session, payload: PlantillaCreate, suscriptor_id: UUID) -> PlantillaEncuesta:
    plantilla = PlantillaEncuesta(**payload.model_dump(), suscriptor_id=suscriptor_id)
    db.add(plantilla)
    db.commit()
    db.refresh(plantilla)
    return plantilla

def get_plantilla(db: Session, plantilla_id: UUID) -> Optional[PlantillaEncuesta]:
    return db.query(PlantillaEncuesta).filter(PlantillaEncuesta.id == plantilla_id).first()

def get_plantilla_con_preguntas(db: Session, plantilla_id: UUID) -> Optional[PlantillaEncuesta]:
    return (
        db.query(PlantillaEncuesta)
        .options(
            joinedload(PlantillaEncuesta.preguntas)
            .joinedload(PreguntaEncuesta.opciones)
        )
        .filter(PlantillaEncuesta.id == plantilla_id)
        .first()
    )

def list_plantillas(db: Session, suscriptor_id: UUID) -> List[PlantillaEncuesta]:
    return (
        db.query(PlantillaEncuesta)
        .filter(PlantillaEncuesta.suscriptor_id == suscriptor_id)
        .all()
    )

def update_plantilla(db: Session, plantilla_id: UUID, payload: PlantillaUpdate) -> Optional[PlantillaEncuesta]:
    plantilla = get_plantilla(db, plantilla_id)
    if not plantilla:
        return None
    
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plantilla, field, value)
    
    db.commit()
    db.refresh(plantilla)
    return plantilla

def delete_plantilla(db: Session, plantilla_id: UUID) -> bool:
    plantilla = get_plantilla(db, plantilla_id)
    if not plantilla:
        return False
    db.delete(plantilla)
    db.commit()
    return True