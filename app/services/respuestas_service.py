from typing import List, Optional, Dict
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException, status
from thefuzz import fuzz

from app.core.constants import ESTADO_RESPONDIDO
from app.models.survey import RespuestaEncuesta, RespuestaPregunta, EntregaEncuesta
from app.schemas.respuestas_schema import RespuestaEncuestaCreate, RespuestaEncuestaUpdate
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
    
    # Crear la respuesta principal
    respuesta = RespuestaEncuesta(
        entrega_id=entrega_id,
        puntuacion=payload.puntuacion,
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
    Convierte el historial de una conversación en una respuesta de encuesta estructurada
    """
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega:
        raise ValueError("Entrega no encontrada")

    # Inicializar respuestas
    respuestas_preguntas = []
    preguntas = {p.id: p for p in entrega.campana.plantilla.preguntas}
    puntuacion_total = 0
    count_preguntas = 0

    # Procesar el historial para extraer respuestas
    for mensaje in historial:
        if mensaje["role"] == "user":
            pregunta_actual_id = entrega.conversacion.pregunta_actual_id
            if pregunta_actual_id not in preguntas:
                continue

            pregunta = preguntas[pregunta_actual_id]
            respuesta = {
                "pregunta_id": pregunta.id,
                "tipo_pregunta_id": pregunta.tipo_pregunta_id
            }

            # Procesar según tipo de pregunta
            if pregunta.tipo_pregunta_id == 1:  # Texto
                respuesta["texto"] = mensaje["content"]
            
            elif pregunta.tipo_pregunta_id == 2:  # Número
                try:
                    numero = float(mensaje["content"])
                    respuesta["numero"] = numero
                    puntuacion_total += numero
                    count_preguntas += 1
                except ValueError:
                    continue
            
            elif pregunta.tipo_pregunta_id == 3:  # Select
                # Buscar la opción que mejor coincida con la respuesta
                mejor_opcion = None
                mejor_coincidencia = 0
                for opcion in pregunta.opciones:
                    coincidencia = fuzz.ratio(
                        mensaje["content"].lower(), 
                        opcion.texto.lower()
                    )
                    if coincidencia > mejor_coincidencia:
                        mejor_coincidencia = coincidencia
                        mejor_opcion = opcion
                
                if mejor_opcion and mejor_coincidencia > 70:
                    respuesta["opcion_id"] = mejor_opcion.id
            
            elif pregunta.tipo_pregunta_id == 4:  # Multiselect
                opciones_seleccionadas = []
                for opcion in pregunta.opciones:
                    if fuzz.partial_ratio(
                        mensaje["content"].lower(), 
                        opcion.texto.lower()
                    ) > 70:
                        opciones_seleccionadas.append(opcion.id)
                
                if opciones_seleccionadas:
                    respuesta["opcion_ids"] = opciones_seleccionadas

            respuestas_preguntas.append(respuesta)

    # Calcular puntuación promedio para preguntas numéricas
    puntuacion_final = (
        puntuacion_total / count_preguntas 
        if count_preguntas > 0 
        else None
    )

    # Crear la respuesta
    respuesta = RespuestaEncuesta(
        entrega_id=entrega_id,
        puntuacion=puntuacion_final,
        raw_payload={"historial": historial}
    )
    db.add(respuesta)
    
    # Crear respuestas individuales
    for resp in respuestas_preguntas:
        pregunta_resp = RespuestaPregunta(
            respuesta_id=respuesta.id,
            **resp
        )
        db.add(pregunta_resp)

    # Marcar la entrega como respondida
    mark_as_responded(db, entrega_id)
    
    db.commit()
    db.refresh(respuesta)
    return respuesta