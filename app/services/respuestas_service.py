from typing import List, Optional, Dict
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException, status
from thefuzz import fuzz

from app.core.constants import ESTADO_RESPONDIDO
from app.models.survey import PreguntaEncuesta, RespuestaEncuesta, RespuestaPregunta, EntregaEncuesta, RespuestaTemp
from app.schemas.respuestas_schema import RespuestaEncuestaCreate, RespuestaEncuestaUpdate, RespuestaPreguntaCreate
from app.services.shared_service import get_entrega_con_plantilla, mark_as_responded

def validate_entrega_status(db: Session, entrega_id: UUID) -> EntregaEncuesta:
    """Valida que la entrega exista y pueda recibir respuestas"""
    entrega = (
        db.query(EntregaEncuesta)
        .filter(EntregaEncuesta.id == entrega_id)
        .first()
    )
    
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada"
        )
    
    if entrega.estado_id == ESTADO_RESPONDIDO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta encuesta ya ha sido respondida"
        )
    
    return entrega

def create_respuesta(
    db: Session, 
    entrega_id: UUID, 
    payload: RespuestaEncuestaCreate
) -> RespuestaEncuesta:
    # Validar estado de la entrega
    entrega = validate_entrega_status(db, entrega_id)
    
    # Crear la respuesta principal (sin puntuación)
    respuesta = RespuestaEncuesta(
        entrega_id=entrega_id,
        raw_payload=payload.raw_payload
    )
    db.add(respuesta)
    db.flush()

    # Crear las respuestas a preguntas individuales
    for resp_pregunta in payload.respuestas_preguntas:
        pregunta_resp = RespuestaPregunta(
            respuesta_id=respuesta.id,
            **resp_pregunta.model_dump()
        )
        db.add(pregunta_resp)

    # Marcar la entrega como respondida
    mark_as_responded(db, entrega_id)
    
    db.commit()
    db.refresh(respuesta)
    return respuesta

def get_respuesta(db: Session, respuesta_id: UUID) -> Optional[RespuestaEncuesta]:
    return (
        db.query(RespuestaEncuesta)
        .options(joinedload(RespuestaEncuesta.respuestas_preguntas))
        .filter(RespuestaEncuesta.id == respuesta_id)
        .first()
    )

def list_respuestas_by_entrega(
    db: Session, 
    entrega_id: UUID
) -> List[RespuestaEncuesta]:
    return (
        db.query(RespuestaEncuesta)
        .options(joinedload(RespuestaEncuesta.respuestas_preguntas))
        .filter(RespuestaEncuesta.entrega_id == entrega_id)
        .all()
    )

def update_respuesta(
    db: Session, 
    respuesta_id: UUID, 
    payload: RespuestaEncuestaUpdate
) -> Optional[RespuestaEncuesta]:
    respuesta = get_respuesta(db, respuesta_id)
    if not respuesta:
        return None

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(respuesta, field, value)
    
    db.commit()
    db.refresh(respuesta)
    return respuesta

def delete_respuesta(db: Session, respuesta_id: UUID) -> bool:
    respuesta = get_respuesta(db, respuesta_id)
    if not respuesta:
        return False
    db.delete(respuesta)
    db.commit()
    return True

async def crear_respuesta_encuesta(
    db: Session, 
    entrega_id: UUID, 
    historial: List[Dict]
) -> RespuestaEncuesta:
    """
    Crea una respuesta de encuesta a partir del historial de conversación
    """
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega:
        raise ValueError("Entrega no encontrada")
    
    # Obtener todas las preguntas de la plantilla ordenadas
    preguntas = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.plantilla_id == entrega.campana.plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .options(joinedload(PreguntaEncuesta.opciones))
        .all()
    )
    
    if not preguntas:
        raise ValueError("No hay preguntas en la plantilla")
    
    # Mapear preguntas por ID para acceso fácil
    preguntas_map = {str(p.id): p for p in preguntas}
    
    # Identificar el inicio de cada pregunta en el historial
    preguntas_indices = []
    
    for i, msg in enumerate(historial):
        if msg["role"] == "assistant":
            # Buscar qué pregunta podría estar en este mensaje
            mensaje_texto = msg["content"].lower()
            for p in preguntas:
                # Si el texto de la pregunta está en el mensaje del asistente
                if p.texto.lower() in mensaje_texto:
                    preguntas_indices.append((i, str(p.id)))
                    break
    
    # Preparar la estructura para las respuestas
    respuestas_preguntas = []
    
    # Procesar cada pregunta identificada y su respuesta
    for i, (msg_idx, pregunta_id) in enumerate(preguntas_indices):
        # Obtener la pregunta correspondiente
        pregunta = preguntas_map.get(pregunta_id)
        if not pregunta:
            continue
        
        # Buscar la respuesta del usuario (primer mensaje "user" después del mensaje del asistente)
        respuesta_texto = None
        for j in range(msg_idx + 1, len(historial)):
            if historial[j]["role"] == "user":
                respuesta_texto = historial[j]["content"]
                break
        
        if not respuesta_texto:
            continue  # No hay respuesta para esta pregunta
        
        # Procesar según tipo de pregunta
        if pregunta.tipo_pregunta_id == 1:  # Texto
            respuesta_pregunta = RespuestaPreguntaCreate(
                pregunta_id=pregunta.id,
                texto=respuesta_texto,
                numero=None,
                opcion_id=None
            )
            respuestas_preguntas.append(respuesta_pregunta)
        
        elif pregunta.tipo_pregunta_id == 2:  # Número
            try:
                numero = float(respuesta_texto.strip())
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta.id,
                    texto=None,
                    numero=numero,
                    opcion_id=None
                )
                respuestas_preguntas.append(respuesta_pregunta)
            except ValueError:
                # Si no es número válido, guardar como texto
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta.id,
                    texto=respuesta_texto,
                    numero=None,
                    opcion_id=None
                )
                respuestas_preguntas.append(respuesta_pregunta)
        
        elif pregunta.tipo_pregunta_id == 3:  # Select (opción única)
            # Buscar la opción seleccionada exactamente
            opcion_id = None
            for opcion in pregunta.opciones:
                if respuesta_texto.strip() == opcion.texto:
                    opcion_id = opcion.id
                    break
                    
            if opcion_id:
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta.id,
                    texto=None,
                    numero=None,
                    opcion_id=opcion_id
                )
                respuestas_preguntas.append(respuesta_pregunta)
        
        elif pregunta.tipo_pregunta_id == 4:  # Multiselect
            # Para multiselect, crear una respuesta para cada opción seleccionada
            respuestas = [r.strip() for r in respuesta_texto.split(',')]
            
            for respuesta in respuestas:
                for opcion in pregunta.opciones:
                    if respuesta == opcion.texto:
                        respuesta_pregunta = RespuestaPreguntaCreate(
                            pregunta_id=pregunta.id,
                            texto=None,
                            numero=None,
                            opcion_id=opcion.id
                        )
                        respuestas_preguntas.append(respuesta_pregunta)
                        break
    
    # Crear el esquema de respuesta encuesta con raw_payload
    respuesta_schema = RespuestaEncuestaCreate(
        raw_payload={"historial": historial},
        respuestas_preguntas=respuestas_preguntas
    )
    
    # Crear la respuesta en la base de datos
    respuesta = create_respuesta(db, entrega_id, respuesta_schema)
    
    # Marcar la entrega como respondida
    mark_as_responded(db, entrega_id)
    
    return respuesta