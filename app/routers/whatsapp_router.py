"""
app/routers/whatsapp_router.py
------------------------------
Router FastAPI para integrar Whapi con el flujo de encuestas.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.survey import PreguntaEncuesta
from app.services import whatsapp_service as ws
from app.services.whatsapp_parser import parse_webhook
from app.services.entregas_service import (
    get_entrega_by_destinatario,
    iniciar_conversacion_whatsapp,
)
from app.services.conversacion_service import procesar_respuesta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# Estado en memoria – usa Redis en prod
conversaciones_estado: Dict[str, str] = {}


# --------------------------------------------------------------------------- #
# HELPERS
# --------------------------------------------------------------------------- #

async def _send_first_question(db: Session, entrega_id: UUID, chat_id: str) -> None:
    """Crea la conversación y envía la primera pregunta."""
    conv = await iniciar_conversacion_whatsapp(db, entrega_id)
    pregunta = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.id == conv.pregunta_actual_id)
        .first()
    )
    if not pregunta:
        raise ValueError("No se pudo obtener la pregunta inicial")

    if pregunta.tipo_pregunta_id in (3, 4):
        opciones = [op.texto for op in pregunta.opciones]
        await ws.send_list(chat_id, pregunta.texto, opciones)
    else:
        await ws.send_text(chat_id, pregunta.texto)


async def _send_next(db: Session, resultado: Dict, chat_id: str) -> None:
    """Envía la siguiente pregunta según su tipo."""
    if resultado.get("opciones") and resultado.get("tipo_pregunta") in (3, 4):
        await ws.send_list(
            chat_id,
            resultado["siguiente_pregunta"],
            resultado["opciones"],
        )
    else:
        await ws.send_text(chat_id, resultado["siguiente_pregunta"])


# --------------------------------------------------------------------------- #
# ENDPOINT PRINCIPAL
# --------------------------------------------------------------------------- #

@router.post("/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    payload = json.loads(body.decode("utf-8"))
    data = parse_webhook(payload)

    # 0) Verificación de Whapi (GET emulado como POST)
    if payload.get("hubVerificationToken"):
        if payload["hubVerificationToken"] == settings.WHAPI_TOKEN:
            return {"success": True, "message": "Webhook verified"}
        raise HTTPException(status_code=403, detail="Invalid verification token")

    # 1) Estados de entrega
    if data["kind"] == "status":
        return {"success": True, "message": "Status ignored"}

    # 2) Ignorados
    if data["kind"] in ("own", "non_text", "unknown"):
        return {"success": True, "message": f"Ignored {data['kind']}"}

    # 3) Error de parser
    if data["kind"] == "error":
        logger.error("Parser error: %s", data["error"])
        return {"success": False, "error": data["error"]}

    # 4) Mensaje válido
    numero   = data["from_number"]
    texto    = data["text"].strip()
    chat_id  = f"{numero}@c.us"

    estado_actual = conversaciones_estado.get(chat_id, "esperando_confirmacion")
    logger.info("Mensaje de %s, estado %s: %s", numero, estado_actual, texto)

    # ---------- localizar entrega ----------
    entrega = get_entrega_by_destinatario(db, telefono=numero)
    if not entrega:
        await ws.send_text(
            chat_id,
            "Hola 👋 No encontré una encuesta pendiente para este número."
        )
        return {"success": True, "message": "No entrega"}

    # ------------------------------------------------------------------ #
    # ESTADO: esperando_confirmacion
    # ------------------------------------------------------------------ #
    if estado_actual == "esperando_confirmacion":
        normal = texto.lower().replace("í", "i")
        es_si = normal in ("si", "yes", "ok") or data.get("payload_id") == "btn_si"
        es_no = normal in ("no", "nop")       or data.get("payload_id") == "btn_no"

        if es_si:
            await _send_first_question(db, entrega.id, chat_id)
            conversaciones_estado[chat_id] = "encuesta_en_progreso"
            return {"success": True, "message": "Survey started"}

        if es_no:
            await ws.send_text(
                chat_id,
                "Entendido. Cuando desees empezar, escribe INICIAR."
            )
            return {"success": True, "message": "Survey declined"}

        await ws.send_confirm(
            chat_id,
            "Responde 'Sí' para comenzar la encuesta ahora o 'No' para más tarde."
        )
        return {"success": True, "message": "Confirmation requested"}

    # ------------------------------------------------------------------ #
    # ESTADO: encuesta_en_progreso
    # ------------------------------------------------------------------ #
    if estado_actual == "encuesta_en_progreso":
        try:
            # entrega.conversacion es lista -> usamos la primera o creamos una
            conv = entrega.conversacion[0] if entrega.conversacion else None
            if not conv:
                conv = await iniciar_conversacion_whatsapp(db, entrega.id)

            resultado = await procesar_respuesta(db, conv.id, texto)

            if "error" in resultado:
                await ws.send_text(chat_id, resultado["error"])
                return {"success": True, "message": "Invalid answer"}

            if resultado.get("completada"):
                conversaciones_estado.pop(chat_id, None)
                msg = "¡Gracias por completar la encuesta! 😊"
                if rid := resultado.get("respuesta_id"):
                    msg += f"\nCódigo: {rid[:8]}"
                await ws.send_text(chat_id, msg)
                return {"success": True, "message": "Survey done"}

            await _send_next(db, resultado, chat_id)
            return {"success": True, "message": "Next question sent"}

        except Exception:
            logger.error("ERROR procesando respuesta", exc_info=True)
            await ws.send_text(
                chat_id,
                "Ocurrió un error. Escribe INICIAR para reiniciar."
            )
            return {"success": False, "error": "exception"}

    # ------------------------------------------------------------------ #
    # Comando INICIAR (en cualquier estado)
    # ------------------------------------------------------------------ #
    if texto.upper() == "INICIAR":
        conversaciones_estado[chat_id] = "esperando_confirmacion"
        nombre = entrega.destinatario.nombre or "Hola"
        await ws.send_confirm(
            chat_id,
            f"{nombre}, ¿deseas comenzar la encuesta "
            f"'{entrega.campana.nombre}' ahora?"
        )
        return {"success": True, "message": "Confirmation requested"}

    # ------------------------------------------------------------------ #
    # Default → pedir INICIAR
    # ------------------------------------------------------------------ #
    await ws.send_text(
        chat_id,
        "Para iniciar o continuar la encuesta escribe INICIAR."
    )
    conversaciones_estado[chat_id] = "esperando_confirmacion"
    return {"success": True, "message": "State reset"}


# --------------------------------------------------------------------------- #
# UTILIDADES EXTRA
# --------------------------------------------------------------------------- #

@router.get("/webhook")
async def verify_webhook(request: Request):
    mode      = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token     = request.query_params.get("hub.verify_token")
    if mode == "subscribe" and token == settings.WHAPI_TOKEN:
        return Response(content=challenge)
    raise HTTPException(status_code=403, detail="Invalid verify token")


@router.post("/reset/{numero}")
async def reset_conversation(numero: str):
    chat_id = numero if "@c.us" in numero else f"{numero}@c.us"
    old = conversaciones_estado.pop(chat_id, None)
    if old:
        return {"success": True, "estado_anterior": old}
    return {"success": False, "message": "No había estado"}


@router.get("/status")
async def get_status():
    resumen: Dict[str, int] = {}
    for est in conversaciones_estado.values():
        resumen[est] = resumen.get(est, 0) + 1
    return {
        "total": len(conversaciones_estado),
        "resumen": resumen,
        "conversaciones": conversaciones_estado,
    }


@router.post("/send")
async def manual_send(
    numero: str, mensaje: str, opciones: List[str] | None = None
):
    if opciones:
        return await ws.send_list(numero, mensaje, opciones)
    return await ws.send_text(numero, mensaje)
