from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException, logger, status

from app.core.constants import (
    ESTADO_PENDIENTE, ESTADO_ENVIADO, 
    ESTADO_RESPONDIDO, ESTADO_FALLIDO
)
from app.models.survey import (
    CampanaEncuesta, ConversacionEncuesta, 
    Destinatario, EntregaEncuesta, 
    PlantillaEncuesta, PreguntaEncuesta
)
from app.services.whatsapp_service import enviar_mensaje_whatsapp
from app.schemas.conversacion_schema import Mensaje
from app.schemas.entregas_schema import EntregaCreate, EntregaUpdate
from app.services.conversacion_service import generar_siguiente_pregunta
from app.services.shared_service import get_entrega_con_plantilla

def create_entrega(
    db: Session, 
    campana_id: UUID, 
    payload: EntregaCreate
) -> EntregaEncuesta:
    entrega = EntregaEncuesta(
        **payload.model_dump(),
        campana_id=campana_id,
        estado_id=ESTADO_PENDIENTE  # Estado inicial: pendiente
    )
    db.add(entrega)
    db.commit()
    db.refresh(entrega)
    return entrega

def get_entrega(db: Session, entrega_id: UUID) -> Optional[EntregaEncuesta]:
    return (
        db.query(EntregaEncuesta)
        .options(
            joinedload(EntregaEncuesta.destinatario),
            joinedload(EntregaEncuesta.respuestas)
        )
        .filter(EntregaEncuesta.id == entrega_id)
        .first()
    )

def list_entregas(
    db: Session, 
    campana_id: UUID,
    skip: int = 0,
    limit: int = 100
) -> List[EntregaEncuesta]:
    return (
        db.query(EntregaEncuesta)
        .filter(EntregaEncuesta.campana_id == campana_id)
        .offset(skip)
        .limit(limit)
        .all()
    )

def update_entrega(
    db: Session, 
    entrega_id: UUID, 
    payload: EntregaUpdate
) -> Optional[EntregaEncuesta]:
    entrega = get_entrega(db, entrega_id)
    if not entrega:
        return None

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entrega, field, value)
    
    db.commit()
    db.refresh(entrega)
    return entrega

def delete_entrega(db: Session, entrega_id: UUID) -> bool:
    entrega = get_entrega(db, entrega_id)
    if not entrega:
        return False
    db.delete(entrega)
    db.commit()
    return True

def mark_as_sent(db: Session, entrega_id: UUID) -> Optional[EntregaEncuesta]:
    """Marca una entrega como enviada"""
    entrega = get_entrega(db, entrega_id)
    if not entrega:
        return None
    
    if entrega.estado_id != ESTADO_PENDIENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede marcar como enviada. Estado actual: {entrega.estado_id}"
        )
    
    entrega.estado_id = ESTADO_ENVIADO
    entrega.enviado_en = datetime.now()
    db.commit()
    db.refresh(entrega)
    return entrega

def mark_as_responded(db: Session, entrega_id: UUID) -> Optional[EntregaEncuesta]:
    """Marca una entrega como respondida"""
    entrega = get_entrega(db, entrega_id)
    if not entrega:
        return None
    
    if entrega.estado_id not in [ESTADO_ENVIADO, ESTADO_PENDIENTE]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede marcar como respondida. Estado actual: {entrega.estado_id}"
        )
    
    entrega.estado_id = ESTADO_RESPONDIDO
    entrega.respondido_en = datetime.now()
    db.commit()
    db.refresh(entrega)
    return entrega

def mark_as_failed(db: Session, entrega_id: UUID, reason: str = None) -> Optional[EntregaEncuesta]:
    """Marca una entrega como fallida"""
    entrega = get_entrega(db, entrega_id)
    if not entrega:
        return None
    
    if entrega.estado_id == ESTADO_RESPONDIDO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede marcar como fallida una entrega ya respondida"
        )
    
    entrega.estado_id = ESTADO_FALLIDO
    db.commit()
    db.refresh(entrega)
    return entrega

def get_entrega_by_destinatario(
    db: Session, 
    email: Optional[str] = None, 
    telefono: Optional[str] = None
) -> Optional[EntregaEncuesta]:
    """Busca una entrega por el email o teléfono del destinatario"""
    if not email and not telefono:
        return None

    query = db.query(EntregaEncuesta).join(EntregaEncuesta.destinatario)
    
    if email:
        query = query.filter(Destinatario.email == email)
    if telefono:
        query = query.filter(Destinatario.telefono == telefono)
        
    return query.first()

async def iniciar_conversacion_whatsapp(db: Session, entrega_id: UUID):
    """Inicia una conversación de WhatsApp para una entrega"""
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega or not entrega.destinatario.telefono:
        raise ValueError("Entrega no válida o sin número de teléfono")

    # Obtener la primera pregunta de la plantilla
    primera_pregunta = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.plantilla_id == entrega.campana.plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .first()
    )
    
    if not primera_pregunta:
        raise ValueError("La plantilla no tiene preguntas")

    # Crear conversación
    conversacion = ConversacionEncuesta(
        entrega_id=entrega_id,
        pregunta_actual_id=primera_pregunta.id
    )
    db.add(conversacion)
    
    # Generar saludo y primera pregunta
    texto_inicial = await generar_siguiente_pregunta(
        [],
        primera_pregunta.texto,
        primera_pregunta.tipo_pregunta_id
    )
    
    mensaje_inicial = Mensaje(role="assistant", content=texto_inicial)
    conversacion.historial.append(mensaje_inicial.dict())
    
    db.commit()
    
    # Enviar mensaje inicial por WhatsApp
    await enviar_mensaje_whatsapp(entrega.destinatario.telefono, texto_inicial)
    
    return conversacion

async def create_entrega(
    db: Session, 
    campana_id: UUID, 
    payload: EntregaCreate
) -> EntregaEncuesta:
    # Create base entrega
    entrega = EntregaEncuesta(
        **payload.model_dump(),
        campana_id=campana_id,
        estado_id=ESTADO_PENDIENTE
    )
    db.add(entrega)
    db.commit()
    db.refresh(entrega)

    # Si es canal WhatsApp, iniciar conversación automáticamente
    if payload.canal_id == 2:  # WhatsApp
        try:
            await iniciar_conversacion_whatsapp(db, entrega.id)
            # Marcar como enviada
            entrega.estado_id = ESTADO_ENVIADO
            entrega.enviado_en = datetime.now()
            db.commit()
            db.refresh(entrega)
        except Exception as e:
            entrega.estado_id = ESTADO_FALLIDO
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error iniciando conversación: {str(e)}"
            )

    return entrega