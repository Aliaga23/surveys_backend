import json
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.models.survey import VapiCallRelation
from app.schemas.respuestas_schema import RespuestaEncuestaCreate, RespuestaPreguntaCreate
from app.services.respuestas_service import create_respuesta
from app.services.entregas_service import get_entrega, mark_as_failed, mark_as_responded

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
        print(f"Webhook Vapi recibido: {payload.get('type')}")
    except json.JSONDecodeError:
        print("Error decodificando JSON del webhook de Vapi")
        return {"success": False, "error": "Invalid JSON"}
    
    # Verificar el tipo de evento según la documentación oficial
    event_type = payload.get("type")
    
    # Manejar diferentes tipos de eventos
    if event_type == "call.completed":
        return await procesar_respuestas_vapi(payload, db)
    elif event_type == "call.failed":
        return await procesar_llamada_fallida(payload, db, "Llamada fallida")
    elif event_type == "call.no_answer":
        return await procesar_llamada_fallida(payload, db, "Sin respuesta")
    elif event_type == "call.busy":
        return await procesar_llamada_fallida(payload, db, "Línea ocupada")
    else:
        print(f"Evento de Vapi recibido pero no procesado: {event_type}")
        return {"success": True, "message": "Event received"}

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
        # Obtener datos estructurados del análisis
        structured_data = payload.get("call", {}).get("analysis", {}).get("structuredData", {})
        if not structured_data:
            return {"success": False, "error": "No structured data found in response"}
        
        # Procesar respuestas - usar exactamente los IDs proporcionados
        respuestas_raw = structured_data.get("respuestas_preguntas", [])
        puntuacion = structured_data.get("puntuacion")
        
        # Crear las respuestas a preguntas
        respuestas_preguntas = []
        for resp in respuestas_raw:
            pregunta_id = resp.get("pregunta_id")
            if not pregunta_id:
                continue
                
            # Asegurarnos de usar exactamente el ID proporcionado
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
        
        # Marcar la entrega como respondida
        mark_as_responded(db, entrega_id)
        
        return {
            "success": True,
            "respuesta_id": str(respuesta.id)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

async def procesar_llamada_fallida(payload: dict, db: Session, motivo: str):
    """
    Procesa eventos de llamadas Vapi fallidas
    """
    call_id = payload.get("call", {}).get("id")
    if not call_id:
        print("No se encontró call_id en el webhook de llamada fallida")
        return {"success": False, "error": "Missing call_id"}
    
    # Buscar la relación entre call_id y entrega_id
    relacion = db.query(VapiCallRelation).filter(VapiCallRelation.call_id == call_id).first()
    if not relacion:
        print(f"No se encontró relación para call_id: {call_id}")
        return {"success": False, "error": "Call ID not found in relations"}
    
    entrega_id = relacion.entrega_id
    print(f"Procesando llamada fallida para entrega: {entrega_id}, motivo: {motivo}")
    
    try:
        # Marcar la entrega como fallida
        entrega_actualizada = mark_as_failed(db, entrega_id)
        if entrega_actualizada:
            print(f"Entrega {entrega_id} marcada como fallida")
            return {"success": True, "message": "Entrega marked as failed"}
        else:
            print(f"No se encontró la entrega {entrega_id}")
            return {"success": False, "error": "Entrega not found"}
            
    except Exception as e:
        print(f"Error procesando llamada fallida: {str(e)}")
        return {"success": False, "error": str(e)}
