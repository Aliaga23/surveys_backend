from typing import List, Optional, Dict
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException, status
from thefuzz import fuzz

from app.core.constants import ESTADO_RESPONDIDO
from app.models.survey import PreguntaEncuesta, RespuestaEncuesta, RespuestaPregunta, EntregaEncuesta
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
    Convierte el historial de una conversación en una respuesta de encuesta estructurada
    """
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega:
        raise ValueError("Entrega no encontrada")
    
    # Obtener todas las preguntas de la plantilla ordenadas
    preguntas = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.plantilla_id == entrega.campana.plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )
    
    if not preguntas:
        raise ValueError("No hay preguntas en la plantilla")
    
    # Mapear preguntas por ID para acceso fácil
    preguntas_map = {p.id: p for p in preguntas}
    
    # Identificar el inicio de cada pregunta en el historial
    preguntas_indices = []
    pregunta_actual = None
    
    for i, msg in enumerate(historial):
        if msg["role"] == "assistant":
            # Buscar qué pregunta podría estar en este mensaje
            mensaje_texto = msg["content"].lower()
            for p in preguntas:
                # Si el texto de la pregunta está en el mensaje del asistente
                if p.texto.lower() in mensaje_texto:
                    pregunta_actual = p
                    preguntas_indices.append((i, p.id))
                    break
    
    # Preparar estructura para las respuestas
    respuestas = []
    
    # Procesar cada pregunta identificada y su respuesta
    for i, (msg_idx, pregunta_id) in enumerate(preguntas_indices):
        pregunta = preguntas_map[pregunta_id]
        
        # Buscar la respuesta del usuario (primer mensaje "user" después del mensaje del asistente)
        respuesta_texto = None
        for j in range(msg_idx + 1, len(historial)):
            if historial[j]["role"] == "user":
                respuesta_texto = historial[j]["content"]
                break
        
        if not respuesta_texto:
            continue  # No hay respuesta para esta pregunta
        
        # Base de la respuesta con ID de pregunta y tipo
        respuesta_item = {
            "pregunta_id": str(pregunta.id),
            "tipo_pregunta_id": pregunta.tipo_pregunta_id
        }
        
        # Procesar según tipo de pregunta
        if pregunta.tipo_pregunta_id == 1:  # Texto
            respuesta_item["texto"] = respuesta_texto
        
        elif pregunta.tipo_pregunta_id == 2:  # Número
            try:
                numero = float(respuesta_texto.strip())
                respuesta_item["numero"] = numero
            except ValueError:
                # Si no es número válido, guardar como texto
                respuesta_item["texto"] = respuesta_texto
        
        elif pregunta.tipo_pregunta_id == 3:  # Select
            # Buscar la opción que mejor coincide
            mejor_opcion = None
            mejor_score = 0
            for opcion in pregunta.opciones:
                score = fuzz.ratio(respuesta_texto.lower(), opcion.texto.lower())
                if score > mejor_score:
                    mejor_score = score
                    mejor_opcion = opcion
            
            if mejor_opcion and mejor_score > 70:
                respuesta_item["opcion_id"] = str(mejor_opcion.id)
        
        elif pregunta.tipo_pregunta_id == 4:  # Multiselect
            # Para multiselect, intentamos encontrar la mejor opción también
            # Aunque idealmente deberíamos identificar múltiples opciones
            mejor_opcion = None
            mejor_score = 0
            for opcion in pregunta.opciones:
                score = fuzz.ratio(respuesta_texto.lower(), opcion.texto.lower())
                if score > mejor_score:
                    mejor_score = score
                    mejor_opcion = opcion
            
            if mejor_opcion and mejor_score > 70:
                respuesta_item["opcion_id"] = str(mejor_opcion.id)
        
        respuestas.append(respuesta_item)
    
    # Crear datos para la respuesta
    respuesta_datos = {
        "entrega_id": str(entrega_id),
        "respuestas": respuestas,
    }
    
    # Crear respuesta en la base de datos usando el esquema adecuado
    respuesta_schema = RespuestaEncuestaCreate(
        raw_payload={"historial": historial},
        respuestas_preguntas=[
            RespuestaPreguntaCreate(
                pregunta_id=UUID(r["pregunta_id"]),
                texto=r.get("texto"),
                numero=r.get("numero"),
                opcion_id=UUID(r["opcion_id"]) if r.get("opcion_id") else None
            ) for r in respuestas
        ]
    )
    
    # Crear la respuesta en la base de datos
    respuesta = create_respuesta(db, entrega_id, respuesta_schema)
    
    # Marcar la entrega como respondida
    mark_as_responded(db, entrega_id)
    
    return respuesta