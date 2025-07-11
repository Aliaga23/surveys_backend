from typing import List, Optional, Dict
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException, status
from thefuzz import fuzz
import logging
from app.core.constants import ESTADO_RESPONDIDO
from app.models.survey import PreguntaEncuesta, RespuestaEncuesta, RespuestaPregunta, EntregaEncuesta, RespuestaTemp
from app.schemas.respuestas_schema import RespuestaEncuestaCreate, RespuestaEncuestaUpdate, RespuestaPreguntaCreate
from app.services.shared_service import get_entrega_con_plantilla, mark_as_responded
from decimal import Decimal

logger = logging.getLogger(__name__)
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
    logger.info(f"Creando respuesta de encuesta para entrega: {entrega_id}")
    
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega:
        raise ValueError(f"Entrega {entrega_id} no encontrada")
    
    preguntas = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.plantilla_id == entrega.campana.plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .options(joinedload(PreguntaEncuesta.opciones))
        .all()
    )
    
    if not preguntas:
        raise ValueError("No hay preguntas en la plantilla")
    
    logger.info(f"Se encontraron {len(preguntas)} preguntas en la plantilla")
   
    pares_pregunta_respuesta = []
    
    for i, msg in enumerate(historial):
        logger.debug(f"Mensaje {i}: {msg.get('role')[:5]} - {msg.get('content', '')[:50]}...")
    
    for i, mensaje in enumerate(historial):
        if mensaje.get('role') == 'assistant':
            # Identificar qué pregunta está haciendo el asistente
            texto_asistente = mensaje.get('content', '').lower()
            pregunta_identificada = None
            
            # Buscar la pregunta más similar en el texto del asistente
            for pregunta in preguntas:
                if pregunta.texto.lower() in texto_asistente:
                    pregunta_identificada = pregunta
                    logger.debug(f"Pregunta identificada en mensaje {i}: {pregunta.texto[:30]}...")
                    break
            
            # Si encontramos una pregunta y hay un mensaje de usuario después
            if pregunta_identificada and i + 1 < len(historial) and historial[i + 1].get('role') == 'user':
                respuesta_texto = historial[i + 1].get('content', '')
                pares_pregunta_respuesta.append((pregunta_identificada, respuesta_texto))
                logger.debug(f"Respuesta asociada: {respuesta_texto[:30]}...")
    
    logger.info(f"Se identificaron {len(pares_pregunta_respuesta)} pares pregunta-respuesta")
    
    respuestas_preguntas = []
    
    for pregunta, respuesta_texto in pares_pregunta_respuesta:
        logger.debug(f"Procesando respuesta para pregunta: {pregunta.texto[:30]}...")
        
        if pregunta.tipo_pregunta_id == 1:  # Texto
            respuesta_pregunta = RespuestaPreguntaCreate(
                pregunta_id=pregunta.id,
                texto=respuesta_texto,
                numero=None,
                opcion_id=None
            )
            respuestas_preguntas.append(respuesta_pregunta)
            logger.debug(f"Guardando respuesta TEXTO")
            
        elif pregunta.tipo_pregunta_id == 2:  # Número
            try:
                # Intentar convertir a número
                numero = float(respuesta_texto.strip())
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta.id,
                    texto=None,
                    numero=numero,
                    opcion_id=None
                )
                respuestas_preguntas.append(respuesta_pregunta)
                logger.debug(f"Guardando respuesta NÚMERO: {numero}")
            except ValueError:
                # Si no es un número válido, guardar como texto
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta.id,
                    texto=respuesta_texto,
                    numero=None,
                    opcion_id=None
                )
                respuestas_preguntas.append(respuesta_pregunta)
                logger.debug(f"Guardando respuesta como TEXTO (no es número válido)")
                
        elif pregunta.tipo_pregunta_id == 3:  # Select (opción única)
            # Buscar la opción seleccionada
            opcion_id = None
            
            # Primero buscar coincidencia exacta
            for opcion in pregunta.opciones:
                if respuesta_texto.strip().lower() == opcion.texto.lower():
                    opcion_id = opcion.id
                    logger.debug(f"Opción exacta encontrada: {opcion.texto}")
                    break
            
            # Si no se encuentra coincidencia exacta, buscar coincidencia parcial
            if not opcion_id:
                for opcion in pregunta.opciones:
                    if opcion.texto.lower() in respuesta_texto.lower() or respuesta_texto.lower() in opcion.texto.lower():
                        opcion_id = opcion.id
                        logger.debug(f"Opción parcial encontrada: {opcion.texto}")
                        break
            
            # Crear la respuesta según si se encontró opción o no
            if opcion_id:
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta.id,
                    texto=None,
                    numero=None,
                    opcion_id=opcion_id
                )
                respuestas_preguntas.append(respuesta_pregunta)
                logger.debug(f"Guardando respuesta OPCIÓN")
            else:
                # Si no se encuentra la opción, guardar como texto
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta.id,
                    texto=respuesta_texto,
                    numero=None,
                    opcion_id=None
                )
                respuestas_preguntas.append(respuesta_pregunta)
                logger.debug(f"Guardando como TEXTO (opción no encontrada)")
                
        elif pregunta.tipo_pregunta_id == 4:  # Multiselect
            selecciones = [s.strip().lower() for s in respuesta_texto.split(',')]
            opciones_encontradas = []
            
            for seleccion in selecciones:
                for opcion in pregunta.opciones:
                    if seleccion == opcion.texto.lower() or seleccion in opcion.texto.lower():
                        respuesta_pregunta = RespuestaPreguntaCreate(
                            pregunta_id=pregunta.id,
                            texto=None,
                            numero=None,
                            opcion_id=opcion.id
                        )
                        respuestas_preguntas.append(respuesta_pregunta)
                        opciones_encontradas.append(opcion.texto)
                        logger.debug(f"Opción multiselect encontrada: {opcion.texto}")
                        break
            
            # Si no se encontró ninguna opción, guardar como texto
            if not opciones_encontradas:
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta.id,
                    texto=respuesta_texto,
                    numero=None,
                    opcion_id=None
                )
                respuestas_preguntas.append(respuesta_pregunta)
                logger.debug(f"Guardando como TEXTO (opciones no encontradas)")
    
    if not respuestas_preguntas:
        raise ValueError("No se pudieron extraer respuestas del historial de la conversación")
    
    # Crear el esquema de respuesta encuesta completa
    respuesta_schema = RespuestaEncuestaCreate(
        raw_payload={"historial": historial},
        respuestas_preguntas=respuestas_preguntas
    )
    
    logger.info(f"Creando respuesta final con {len(respuestas_preguntas)} respuestas")
    
    try:
        respuesta = create_respuesta(db, entrega_id, respuesta_schema)
        
        mark_as_responded(db, entrega_id)
        
        logger.info(f"Respuesta creada correctamente con ID: {respuesta.id}")
        return respuesta
    except Exception as e:
        logger.error(f"Error creando respuesta: {str(e)}")
        db.rollback()
        raise ValueError(f"Error al crear respuesta: {str(e)}")
    

async def registrar_respuestas_publicas(
    db: Session,
    entrega_id: UUID,
    payload: dict,
) -> RespuestaEncuesta:
    """
    • Valida la entrega y su plantilla  
    • Crea (o reutiliza) RespuestaEncuesta  
    • Inserta RespuestaPregunta según reglas:
        tipo 1 → texto
        tipo 2 → numero
        tipo 3 → opcion_id (única)
        tipo 4 → varias opciones_ids
    • Marca la entrega como respondida
    Devuelve el objeto RespuestaEncuesta recién guardado
    """
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega:
        raise HTTPException(404, "Entrega no encontrada")

    if entrega.estado_id == ESTADO_RESPONDIDO:
        raise HTTPException(400, "La encuesta ya fue respondida")

    plantilla = entrega.campana.plantilla
    mapa_preguntas: dict[str, PreguntaEncuesta] = {
        str(p.id): p for p in plantilla.preguntas
    }

    # ─── Reutilizar o crear RespuestaEncuesta ────────────────────────────
    r_enc = (
        db.query(RespuestaEncuesta)
        .filter(RespuestaEncuesta.entrega_id == entrega_id)
        .first()
    )
    if not r_enc:
        r_enc = RespuestaEncuesta(entrega_id=entrega_id, raw_payload=payload)
        db.add(r_enc)
        db.commit()
        db.refresh(r_enc)
    else:
        r_enc.raw_payload = payload  # guarda la versión cruda, por si acaso

    # ─── Parsear respuestas_preguntas ────────────────────────────────────
    for item in payload.get("respuestas_preguntas", []):
        qid   = item.get("pregunta_id")
        preg  = mapa_preguntas.get(qid)
        if not preg:                       # id que no pertenece a la plantilla
            continue

        tipo  = preg.tipo_pregunta_id
        texto = item.get("texto")
        num   = item.get("numero")
        op_id = item.get("opcion_id")
        ops   = item.get("opciones_ids", [])
        meta  = item.get("metadatos", {})

        # ── Pregunta abierta texto ───────────────────────────────────────
        if tipo == 1:
            if not texto:                  # se esperaba texto
                continue
            det = RespuestaPregunta(
                respuesta_id=r_enc.id,
                pregunta_id=preg.id,
                texto=texto.strip(),
            )
            db.add(det)

        # ── Pregunta numérica ────────────────────────────────────────────
        elif tipo == 2:
            try:
                numero = Decimal(str(num))
            except Exception:
                continue
            det = RespuestaPregunta(
                respuesta_id=r_enc.id,
                pregunta_id=preg.id,
                numero=numero,
            )
            db.add(det)

        # ── Selección única ──────────────────────────────────────────────
        elif tipo == 3:
            # si viene lista, tomamos el primero; el resto a metadatos
            if not op_id and ops:
                op_id, *sobrantes = ops
                meta.setdefault("sobrantes", sobrantes)
            if not op_id:
                continue
            det = RespuestaPregunta(
                respuesta_id=r_enc.id,
                pregunta_id=preg.id,
                opcion_id=UUID(op_id),
                metadatos=meta,
            )
            db.add(det)

        # ── Selección múltiple ───────────────────────────────────────────
        elif tipo == 4:
            if not ops:
                continue
            for oid in ops:
                det = RespuestaPregunta(
                    respuesta_id=r_enc.id,
                    pregunta_id=preg.id,
                    opcion_id=UUID(oid),
                    metadatos=meta,
                )
                db.add(det)

    db.commit()

    # ─── Finalizar entrega ───────────────────────────────────────────────
    mark_as_responded(db, entrega_id)
    return r_enc