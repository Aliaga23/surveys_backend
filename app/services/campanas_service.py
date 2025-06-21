from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException, status

from app.core.constants import (
    ESTADO_PENDIENTE, ESTADO_ENVIADO, 
    ESTADO_RESPONDIDO, ESTADO_FALLIDO
)
from app.models.survey import (
    CampanaEncuesta, EntregaEncuesta, RespuestaEncuesta, 
    PlantillaEncuesta, PreguntaEncuesta, OpcionEncuesta
)
from app.schemas.campanas_schema import CampanaCreate, CampanaUpdate

# Estados de campaña según la DB
ESTADO_BORRADOR = 1
ESTADO_PROGRAMADA = 2
ESTADO_ENVIADA = 3
ESTADO_CERRADA = 4

def create_campana(db: Session, payload: CampanaCreate, suscriptor_id: UUID) -> CampanaEncuesta:
    campana = CampanaEncuesta(
        **payload.model_dump(),
        suscriptor_id=suscriptor_id,
        estado_id=ESTADO_BORRADOR  
    )
    db.add(campana)
    db.commit()
    db.refresh(campana)
    return campana

def get_campana(db: Session, campana_id: UUID) -> Optional[CampanaEncuesta]:
    return db.query(CampanaEncuesta).filter(CampanaEncuesta.id == campana_id).first()

def list_campanas(db: Session, suscriptor_id: UUID) -> List[CampanaEncuesta]:
    return db.query(CampanaEncuesta).filter(CampanaEncuesta.suscriptor_id == suscriptor_id).all()

def validate_estado_transition(estado_actual: int, nuevo_estado: int):
    """Valida las transiciones permitidas de estados"""
    transiciones_validas = {
        ESTADO_BORRADOR: [ESTADO_PROGRAMADA],
        ESTADO_PROGRAMADA: [ESTADO_ENVIADA, ESTADO_BORRADOR],
        ESTADO_ENVIADA: [ESTADO_CERRADA],
        ESTADO_CERRADA: [] 
    }
    
    if nuevo_estado not in transiciones_validas.get(estado_actual, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transición de estado no válida: {estado_actual} -> {nuevo_estado}"
        )

def update_campana(db: Session, campana_id: UUID, payload: CampanaUpdate) -> Optional[CampanaEncuesta]:
    campana = get_campana(db, campana_id)
    if not campana:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    
    # Validar transición de estado si se está actualizando
    if 'estado_id' in update_data:
        nuevo_estado = update_data['estado_id']
        validate_estado_transition(campana.estado_id, nuevo_estado)
        
        # Validaciones adicionales según el estado
        if nuevo_estado == ESTADO_PROGRAMADA:
            if not campana.plantilla_id and not update_data.get('plantilla_id'):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede programar una campaña sin plantilla"
                )
            if not campana.programada_en and not update_data.get('programada_en'):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Se requiere fecha de programación"
                )
    
    for field, value in update_data.items():
        setattr(campana, field, value)
    
    db.commit()
    db.refresh(campana)
    return campana

def delete_campana(db: Session, campana_id: UUID) -> bool:
    campana = get_campana(db, campana_id)
    if not campana:
        return False
    db.delete(campana)
    db.commit()
    return True

def update_estado_campana(
    db: Session,
    campana_id: UUID,
    nuevo_estado: int,
    check_transitions: bool = True
) -> Optional[CampanaEncuesta]:
    """
    Actualiza el estado de una campaña validando las transiciones permitidas
    """
    campana = get_campana(db, campana_id)
    if not campana:
        return None

    # Validar transiciones permitidas
    if check_transitions:
        transiciones_validas = {
            ESTADO_BORRADOR: [ESTADO_PROGRAMADA],
            ESTADO_PROGRAMADA: [ESTADO_ENVIADA, ESTADO_BORRADOR],
            ESTADO_ENVIADA: [ESTADO_CERRADA],
            ESTADO_CERRADA: []  # Estado final, no permite transiciones
        }

        if nuevo_estado not in transiciones_validas.get(campana.estado_id, []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transición de estado no válida: {campana.estado_id} -> {nuevo_estado}"
            )

    # Validaciones específicas según el estado
    if nuevo_estado == ESTADO_PROGRAMADA:
        if not campana.plantilla_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede programar una campaña sin plantilla"
            )
        if not campana.programada_en:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se requiere fecha de programación"
            )

    campana.estado_id = nuevo_estado
    db.commit()
    db.refresh(campana)
    return campana

def get_campana_full_detail(db: Session, campana_id: UUID) -> Optional[CampanaEncuesta]:
    """Obtiene una campaña con todos sus detalles y relaciones"""
    campana = (
        db.query(CampanaEncuesta)
        .options(
            # Cargar plantilla con sus preguntas y opciones
            joinedload(CampanaEncuesta.plantilla)
            .joinedload(PlantillaEncuesta.preguntas)
            .joinedload(PreguntaEncuesta.opciones),
            
            # Cargar entregas con sus destinatarios y respuestas
            joinedload(CampanaEncuesta.entregas)
            .joinedload(EntregaEncuesta.destinatario),
            
            joinedload(CampanaEncuesta.entregas)
            .joinedload(EntregaEncuesta.respuestas)
            .joinedload(RespuestaEncuesta.respuestas_preguntas)
        )
        .filter(CampanaEncuesta.id == campana_id)
        .first()
    )

    if campana:
        # Agregar contadores
        campana.total_entregas = len(campana.entregas)
        campana.total_respondidas = sum(1 for e in campana.entregas if e.estado_id == 3)  # ESTADO_RESPONDIDO
        campana.total_pendientes = campana.total_entregas - campana.total_respondidas

    return campana
