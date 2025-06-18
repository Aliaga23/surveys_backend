import json
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
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
    evento = payload.get("event")
    
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
    # Extraer datos necesarios
    entrega_id = payload.get("entrega_id")
    respuestas_raw = payload.get("respuestas", [])
    
    if not entrega_id:
        return {"success": False, "error": "Missing entrega_id"}
    
    try:
        # Convertir el entrega_id a UUID
        entrega_id_uuid = UUID(entrega_id)
        
        # Obtener la entrega
        entrega = get_entrega(db, entrega_id_uuid)
        if not entrega:
            return {"success": False, "error": "Entrega not found"}
        
        # Procesar las respuestas
        respuestas_preguntas = []
        puntuacion_total = 0
        count_preguntas_numericas = 0
        
        for resp in respuestas_raw:
            pregunta_id = resp.get("pregunta_id")
            if not pregunta_id:
                continue
                
            respuesta_pregunta = {
                "pregunta_id": UUID(pregunta_id),
                "texto": None,
                "numero": None,
                "opcion_id": None
            }
            
            # Procesar según el tipo de respuesta
            tipo_respuesta = resp.get("tipo")
            if tipo_respuesta == 1:  # Texto
                respuesta_pregunta["texto"] = resp.get("respuesta_texto")
                
            elif tipo_respuesta == 2:  # Número
                try:
                    valor_numerico = float(resp.get("respuesta_numero", 0))
                    respuesta_pregunta["numero"] = valor_numerico
                    puntuacion_total += valor_numerico
                    count_preguntas_numericas += 1
                except (ValueError, TypeError):
                    respuesta_pregunta["texto"] = str(resp.get("respuesta_numero", ""))
                    
            elif tipo_respuesta in [3, 4]:  # Select o Multiselect
                opcion_id = resp.get("respuesta_opcion_id")
                if opcion_id:
                    respuesta_pregunta["opcion_id"] = UUID(opcion_id)
                    respuesta_pregunta["texto"] = resp.get("respuesta_texto", "")
            
            # Añadir la respuesta procesada
            respuestas_preguntas.append(RespuestaPreguntaCreate(**respuesta_pregunta))
        
        # Calcular puntuación promedio
        puntuacion = None
        if count_preguntas_numericas > 0:
            puntuacion = round(puntuacion_total / count_preguntas_numericas, 1)
        
        # Crear la respuesta de la encuesta
        respuesta_schema = RespuestaEncuestaCreate(
            puntuacion=puntuacion,
            raw_payload=payload,
            respuestas_preguntas=respuestas_preguntas
        )
        
        # Guardar en la base de datos
        respuesta = create_respuesta(db, entrega_id_uuid, respuesta_schema)
        
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
    entrega_id = payload.get("entrega_id")
    motivo = payload.get("motivo", "Llamada fallida")
    
    if not entrega_id:
        return {"success": False, "error": "Missing entrega_id"}
    
    try:
        entrega_id_uuid = UUID(entrega_id)
        
        # Marcar la entrega como fallida
        entrega_actualizada = mark_as_failed(db, entrega_id_uuid, motivo)
        if entrega_actualizada:
            return {"success": True, "message": "Entrega marked as failed"}
        else:
            return {"success": False, "error": "Entrega not found or cannot be marked as failed"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}