import json
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.models.survey import VapiCallRelation
from app.schemas.respuestas_schema import RespuestaEncuestaCreate, RespuestaPreguntaCreate
from app.services.respuestas_service import create_respuesta
from app.services.entregas_service import get_entrega, mark_as_failed

router = APIRouter(prefix="/vapi", tags=["Vapi"])

@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook para recibir las respuestas y eventos de Vapi
    """
    # Leer el cuerpo de la solicitud
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid JSON"}
    
    # Verificar el evento
    evento = payload.get("type")  # Vapi usa "type" para el tipo de evento
    
    # Si es un evento de finalización de llamada
    if evento == "call.completed":
        return await procesar_respuestas_vapi(payload, db)
    
    # Si es un evento de llamada fallida
    elif evento in ["call.failed", "call.no_answer", "call.busy"]:
        return await procesar_llamada_fallida(payload, db)
    
    # Cualquier otro evento
    return {"success": True}

async def procesar_respuestas_vapi(payload: dict, db: Session):
    """
    Procesa las respuestas recibidas de una llamada Vapi completada
    """
    # Extraer el ID de la llamada
    call_id = payload.get("call", {}).get("id")
    if not call_id:
        return {"success": False, "error": "Missing call_id"}
    
    # Buscar la relación entre call_id y entrega_id
    relacion = db.query(VapiCallRelation).filter(VapiCallRelation.call_id == call_id).first()
    if not relacion:
        return {"success": False, "error": "Call ID not found in relations"}
    
    entrega_id = relacion.entrega_id
    
    try:
        # Obtener datos estructurados del análisis - ruta exacta según documentación
        structured_data = payload.get("call", {}).get("analysis", {}).get("structuredData", {})
        if not structured_data:
            return {"success": False, "error": "No structured data found in response"}
        
        # Procesar respuestas según el esquema preestablecido
        respuestas_raw = structured_data.get("respuestas_preguntas", [])
        puntuacion = structured_data.get("puntuacion")
        
        # Crear las respuestas a preguntas
        respuestas_preguntas = []
        for resp in respuestas_raw:
            pregunta_id = resp.get("pregunta_id")
            if not pregunta_id:
                continue
                
            respuesta_pregunta = {
                "pregunta_id": UUID(pregunta_id),
                "texto": resp.get("texto"),
                "numero": resp.get("numero"),
                "opcion_id": UUID(resp["opcion_id"]) if resp.get("opcion_id") else None
            }
            
            respuestas_preguntas.append(RespuestaPreguntaCreate(**respuesta_pregunta))
        
        # Crear la respuesta de la encuesta
        respuesta_schema = RespuestaEncuestaCreate(
            puntuacion=puntuacion,
            raw_payload=payload,
            respuestas_preguntas=respuestas_preguntas
        )
        
        # Guardar en la base de datos
        respuesta = create_respuesta(db, entrega_id, respuesta_schema)
        
        return {
            "success": True,
            "respuesta_id": str(respuesta.id)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

async def procesar_llamada_fallida(payload: dict, db: Session):
    """
    Procesa eventos de llamadas Vapi fallidas
    """
    call_id = payload.get("call", {}).get("id")
    if not call_id:
        return {"success": False, "error": "Missing call_id"}
    
    # Buscar la relación entre call_id y entrega_id
    relacion = db.query(VapiCallRelation).filter(VapiCallRelation.call_id == call_id).first()
    if not relacion:
        return {"success": False, "error": "Call ID not found in relations"}
    
    entrega_id = relacion.entrega_id
    
    try:
        # Determinar motivo del fallo
        motivo = payload.get("reason", "Llamada fallida")
        
        # Marcar la entrega como fallida
        entrega_actualizada = mark_as_failed(db, entrega_id, motivo)
        if entrega_actualizada:
            return {"success": True, "message": "Entrega marked as failed"}
        else:
            return {"success": False, "error": "Entrega not found or cannot be marked as failed"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}
