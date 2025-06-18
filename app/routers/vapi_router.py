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
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid JSON"}

    evento = payload.get("event")

    if evento == "call.completed":
        return await procesar_respuestas_vapi(payload, db)
    elif evento in ["call.failed", "call.no_answer", "call.busy"]:
        return await procesar_llamada_fallida(payload, db)
    
    return {"success": True}

async def procesar_respuestas_vapi(payload: dict, db: Session):
    """
    Procesa las respuestas recibidas de una llamada Vapi completada
    """
    call = payload.get("call", {})
    metadata = call.get("metadata", {})
    entrega_id = metadata.get("entrega_id")
    respuestas_raw = payload.get("results", [])

    if not entrega_id:
        return {"success": False, "error": "Missing entrega_id"}

    try:
        entrega_id_uuid = UUID(entrega_id)
        entrega = get_entrega(db, entrega_id_uuid)
        if not entrega:
            return {"success": False, "error": "Entrega not found"}

        respuestas_preguntas = []
        puntuacion_total = 0
        count_preguntas_numericas = 0

        for resp in respuestas_raw:
            pregunta_id = resp.get("questionId")  # ajustado según formato Vapi
            tipo_respuesta = resp.get("type")
            respuesta = resp.get("answer", {})

            if not pregunta_id:
                continue

            respuesta_pregunta = {
                "pregunta_id": UUID(pregunta_id),
                "texto": None,
                "numero": None,
                "opcion_id": None
            }

            if tipo_respuesta == 1:  # Texto
                respuesta_pregunta["texto"] = respuesta.get("text")
            elif tipo_respuesta == 2:  # Número
                try:
                    valor = float(respuesta.get("number", 0))
                    respuesta_pregunta["numero"] = valor
                    puntuacion_total += valor
                    count_preguntas_numericas += 1
                except (ValueError, TypeError):
                    respuesta_pregunta["texto"] = str(respuesta.get("number", ""))
            elif tipo_respuesta in [3, 4]:  # Select o Multiselect
                if "optionId" in respuesta:
                    respuesta_pregunta["opcion_id"] = UUID(respuesta["optionId"])
                    respuesta_pregunta["texto"] = respuesta.get("text", "")

            respuestas_preguntas.append(RespuestaPreguntaCreate(**respuesta_pregunta))

        puntuacion = None
        if count_preguntas_numericas > 0:
            puntuacion = round(puntuacion_total / count_preguntas_numericas, 1)

        respuesta_schema = RespuestaEncuestaCreate(
            puntuacion=puntuacion,
            raw_payload=payload,
            respuestas_preguntas=respuestas_preguntas
        )

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
    call = payload.get("call", {})
    metadata = call.get("metadata", {})
    entrega_id = metadata.get("entrega_id")
    motivo = payload.get("reason", "Llamada fallida")

    if not entrega_id:
        return {"success": False, "error": "Missing entrega_id"}

    try:
        entrega_id_uuid = UUID(entrega_id)
        entrega_actualizada = mark_as_failed(db, entrega_id_uuid, motivo)
        if entrega_actualizada:
            return {"success": True, "message": "Entrega marked as failed"}
        else:
            return {"success": False, "error": "Entrega not found or cannot be marked as failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}
