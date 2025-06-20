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
    print(f"Creando respuesta de encuesta para entrega: {entrega_id}")
    
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
    
    print(f"Se encontraron {len(preguntas)} preguntas en la plantilla")
    
    # Mapear preguntas por ID para acceso fácil
    preguntas_map = {str(p.id): p for p in preguntas}
    
    # Mapear texto de pregunta a ID
    preguntas_texto_map = {p.texto.lower(): p for p in preguntas}
    
    # Identificar preguntas y respuestas en el historial
    pares_pregunta_respuesta = []
    pregunta_actual = None
    
    for i, mensaje in enumerate(historial):
        print(f"Procesando mensaje {i}: {mensaje.get('role')} - {mensaje.get('content')[:30]}...")
        
        if mensaje.get('role') == 'assistant':
            # Buscar qué pregunta está haciendo el asistente
            texto = mensaje.get('content', '').lower()
            
            # Intentar encontrar la pregunta por su texto exacto o parcial
            pregunta_encontrada = None
            for p in preguntas:
                if p.texto.lower() in texto:
                    pregunta_encontrada = p
                    break
            
            if pregunta_encontrada:
                pregunta_actual = pregunta_encontrada
                print(f"Pregunta identificada en mensaje {i}: {pregunta_actual.texto[:30]}...")
        
        elif mensaje.get('role') == 'user' and pregunta_actual:
            # Este es una respuesta a la pregunta anterior
            respuesta = mensaje.get('content', '')
            pares_pregunta_respuesta.append((pregunta_actual, respuesta))
            print(f"Respuesta encontrada en mensaje {i}: {respuesta[:30]}...")
            # No resetear pregunta_actual para manejar casos donde no se identifica bien la siguiente pregunta
    
    print(f"Se encontraron {len(pares_pregunta_respuesta)} pares de pregunta-respuesta")
    
    # Preparar las respuestas para el esquema
    respuestas_preguntas = []
    
    for pregunta, respuesta_texto in pares_pregunta_respuesta:
        print(f"Procesando respuesta para pregunta: {pregunta.texto[:30]}...")
        
        # Procesar según tipo de pregunta
        if pregunta.tipo_pregunta_id == 1:  # Texto
            respuestas_preguntas.append(
                RespuestaPreguntaCreate(
                    pregunta_id=pregunta.id,
                    texto=respuesta_texto,
                    numero=None,
                    opcion_id=None
                )
            )
            print(f"Guardando respuesta TEXTO: {respuesta_texto[:30]}...")
        
        elif pregunta.tipo_pregunta_id == 2:  # Número
            try:
                numero = float(respuesta_texto.strip())
                respuestas_preguntas.append(
                    RespuestaPreguntaCreate(
                        pregunta_id=pregunta.id,
                        texto=None,
                        numero=numero,
                        opcion_id=None
                    )
                )
                print(f"Guardando respuesta NÚMERO: {numero}")
            except ValueError:
                # Si no es un número válido, guardar como texto
                respuestas_preguntas.append(
                    RespuestaPreguntaCreate(
                        pregunta_id=pregunta.id,
                        texto=respuesta_texto,
                        numero=None,
                        opcion_id=None
                    )
                )
                print(f"Guardando respuesta como TEXTO (no es número válido): {respuesta_texto[:30]}...")
        
        elif pregunta.tipo_pregunta_id == 3:  # Select (opción única)
            # Buscar la opción seleccionada
            opcion_seleccionada = None
            print(f"Opciones disponibles para pregunta {pregunta.texto[:30]}:")
            for opcion in pregunta.opciones:
                print(f"  - {opcion.texto} (ID: {opcion.id})")
                if respuesta_texto.strip() == opcion.texto:
                    opcion_seleccionada = opcion
            
            if opcion_seleccionada:
                respuestas_preguntas.append(
                    RespuestaPreguntaCreate(
                        pregunta_id=pregunta.id,
                        texto=None,
                        numero=None,
                        opcion_id=opcion_seleccionada.id
                    )
                )
                print(f"Guardando respuesta OPCIÓN ÚNICA: {opcion_seleccionada.texto} (ID: {opcion_seleccionada.id})")
            else:
                # Si no se encuentra la opción, guardar como texto
                respuestas_preguntas.append(
                    RespuestaPreguntaCreate(
                        pregunta_id=pregunta.id,
                        texto=respuesta_texto,
                        numero=None,
                        opcion_id=None
                    )
                )
                print(f"No se encontró la opción. Guardando como TEXTO: {respuesta_texto[:30]}...")
        
        elif pregunta.tipo_pregunta_id == 4:  # Multiselect
            # Dividir la respuesta por comas
            opciones_texto = [opt.strip() for opt in respuesta_texto.split(',')]
            print(f"Opciones seleccionadas (multiselect): {opciones_texto}")
            
            # Buscar cada opción seleccionada
            for opt_texto in opciones_texto:
                for opcion in pregunta.opciones:
                    if opt_texto == opcion.texto:
                        respuestas_preguntas.append(
                            RespuestaPreguntaCreate(
                                pregunta_id=pregunta.id,
                                texto=None,
                                numero=None,
                                opcion_id=opcion.id
                            )
                        )
                        print(f"Guardando respuesta OPCIÓN MÚLTIPLE: {opcion.texto} (ID: {opcion.id})")
                        break
    
    # Crear el esquema de respuesta encuesta
    respuesta_schema = RespuestaEncuestaCreate(
        raw_payload={"historial": historial},
        respuestas_preguntas=respuestas_preguntas
    )
    
    print(f"Creando respuesta con {len(respuestas_preguntas)} respuestas a preguntas")
    
    # Crear la respuesta en la base de datos
    respuesta = create_respuesta(db, entrega_id, respuesta_schema)
    
    # Marcar la entrega como respondida
    mark_as_responded(db, entrega_id)
    
    print(f"Respuesta creada con ID: {respuesta.id}")
    
    return respuesta