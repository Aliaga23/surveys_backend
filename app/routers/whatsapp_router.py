# app/routers/whatsapp_router.py
# --------------------------------
"""
Router FastAPI para integrar Whapi con el flujo de encuestas.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.survey import EntregaEncuesta, PreguntaEncuesta
from app.services import whatsapp_service as ws
from app.services.whatsapp_parser import parse_webhook
from app.services.entregas_service import (
    get_entrega_by_destinatario,
    iniciar_conversacion_whatsapp,
)
from app.services.conversacion_service import procesar_respuesta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# cache sencillo en memoria (en prod → redis)
conversaciones_estado: Dict[str, str] = {}

# --------------------------------------------------------------------------- #
# HELPERS
# --------------------------------------------------------------------------- #

def _render_multiselect_text(pregunta: PreguntaEncuesta) -> str:
    opciones = "\n".join(f"• {o.texto}" for o in pregunta.opciones)
    return (
        f"{pregunta.texto}\n\n"
        f"Opciones disponibles:\n{opciones}\n\n"
        "Responde escribiendo las opciones que elijas (en cualquier orden)."
    )


async def _send_first_question(db: Session, entrega_id: UUID, chat_id: str) -> None:
    conv = await iniciar_conversacion_whatsapp(db, entrega_id)
    pregunta = db.query(PreguntaEncuesta).get(conv.pregunta_actual_id)

    if not pregunta:
        raise ValueError("No se pudo obtener la primera pregunta")

    if pregunta.tipo_pregunta_id == 3:                     # selección única
        await ws.send_list(
            chat_id,
            pregunta.texto,
            [o.texto for o in pregunta.opciones],
        )

    elif pregunta.tipo_pregunta_id == 4:                   # multiselección
        await ws.send_text(chat_id, _render_multiselect_text(pregunta))

    else:                                                  # texto o numérico
        await ws.send_text(chat_id, pregunta.texto)


async def _send_next(db: Session, res: Dict, chat_id: str) -> None:
    tp = res.get("tipo_pregunta")

    if tp == 3:                                            # selección única
        await ws.send_list(chat_id, res["siguiente_pregunta"], res["opciones"])

    elif tp == 4:                                          # multiselección
        opciones = "\n".join(f"• {o}" for o in res["opciones"])
        await ws.send_text(
            chat_id,
            f"{res['siguiente_pregunta']}\n\n"
            f"Opciones disponibles:\n{opciones}\n\n"
            "Responde escribiendo las opciones que elijas (en cualquier orden)."
        )

    else:                                                  # texto / numérico
        await ws.send_text(chat_id, res["siguiente_pregunta"])


# --------------------------------------------------------------------------- #
# ENDPOINT PRINCIPAL
# --------------------------------------------------------------------------- #

@router.post("/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    # ------------------------------------------------ cuerpo + parser
    payload = json.loads((await request.body()).decode())
    data    = parse_webhook(payload)

    # --- verificación Whapi (hace eco del reto)
    if payload.get("hubVerificationToken"):
        if payload["hubVerificationToken"] == settings.WHAPI_TOKEN:
            return {"success": True, "message": "Webhook verified"}
        raise HTTPException(status_code=403, detail="Invalid verification token")

    # --- ignorados varios
    if data["kind"] in ("status", "own", "non_text", "unknown"):
        return {"success": True, "message": f"Ignored {data['kind']}"}

    if data["kind"] == "error":
        logger.error("Parser error: %s", data["error"])
        return {"success": False, "error": data["error"]}

    # ------------------------------------------------ datos esenciales
    numero     = data["from_number"]
    texto      = data["text"].strip()
    payload_id = data.get("payload_id", "")
    chat_id    = f"{numero}@c.us"

    estado = conversaciones_estado.get(chat_id, "esperando_confirmacion")
    logger.info("Mensaje de %s  |  estado=%s  |  %s", numero, estado, texto)

    # ------------------------------------------------ localizar entrega pendiente
    entrega: EntregaEncuesta | None = get_entrega_by_destinatario(db, telefono=numero)

    if not entrega or entrega.estado_id == 3:  # 3 → respondido
        await ws.send_text(chat_id, "No tengo encuestas pendientes para este número 😊")
        return {"success": True, "message": "No pending delivery"}

    # ------------------------------------------------------------------ #
    # ESTADO: esperando_confirmacion
    # ------------------------------------------------------------------ #
    if estado == "esperando_confirmacion":
        normalized = texto.lower().replace("í", "i")
        confirmado = normalized in ("si", "yes", "ok") or payload_id == "btn_si"
        rechazado  = normalized in ("no", "nop")       or payload_id == "btn_no"

        if confirmado:
            await _send_first_question(db, entrega.id, chat_id)
            conversaciones_estado[chat_id] = "encuesta_en_progreso"
            return {"success": True, "message": "Survey started"}

        if rechazado:
            await ws.send_text(chat_id, "Entendido. Cuando desees empezar escribe INICIAR.")
            return {"success": True, "message": "Survey declined"}

        # cualquier otra cosa → volver a pedir confirmación
        await ws.send_confirm(
            chat_id,
            "Responde 'Sí' para comenzar la encuesta ahora o 'No' para más tarde."
        )
        return {"success": True, "message": "Confirmation requested"}

    # ------------------------------------------------------------------ #
    # ESTADO: encuesta_en_progreso
    # ------------------------------------------------------------------ #
    if estado == "encuesta_en_progreso":
        try:
            conv = entrega.conversacion[0] if entrega.conversacion else await iniciar_conversacion_whatsapp(db, entrega.id)
            resultado = await procesar_respuesta(db, conv.id, texto)

            if "error" in resultado:
                await ws.send_text(chat_id, resultado["error"])
                return {"success": True, "message": "Invalid answer"}

            if resultado.get("completada"):
                conversaciones_estado.pop(chat_id, None)
                await ws.send_text(chat_id, "¡Gracias por completar la encuesta! 😊")
                return {"success": True, "message": "Survey finished"}

            await _send_next(db, resultado, chat_id)
            return {"success": True, "message": "Next question sent"}

        except Exception:
            logger.error("ERROR procesando respuesta", exc_info=True)
            await ws.send_text(chat_id, "Ocurrió un error. Escribe INICIAR para reiniciar.")
            return {"success": False, "error": "exception"}

    # ------------------------------------------------------------------ #
    # Comando INICIAR — en cualquier momento reinicia confirmación
    # ------------------------------------------------------------------ #
    if texto.upper() == "INICIAR":
        conversaciones_estado[chat_id] = "esperando_confirmacion"
        nombre = entrega.destinatario.nombre or "Hola"
        await ws.send_confirm(
            chat_id,
            f"{nombre}, ¿deseas comenzar la encuesta '{entrega.campana.nombre}' ahora?"
        )
        return {"success": True, "message": "Confirmation requested"}

    # ------------------------------------------------------------------ #
    # default → pedir INICIAR
    # ------------------------------------------------------------------ #
    await ws.send_text(chat_id, "Para iniciar o continuar la encuesta escribe INICIAR.")
    conversaciones_estado[chat_id] = "esperando_confirmacion"
    return {"success": True, "message": "State reset"}


# --------------------------------------------------------------------------- #
# UTILIDADES DE MONITOREO / DEBUG
# --------------------------------------------------------------------------- #

@router.get("/webhook")
async def verify_webhook(request: Request):
    if (
        request.query_params.get("hub.mode") == "subscribe"
        and request.query_params.get("hub.verify_token") == settings.WHAPI_TOKEN
    ):
        return Response(content=request.query_params.get("hub.challenge"))
    raise HTTPException(status_code=403, detail="Invalid verify token")


@router.post("/reset/{numero}")
async def reset_conversation(numero: str):
    chat_id = numero if "@c.us" in numero else f"{numero}@c.us"
    prev = conversaciones_estado.pop(chat_id, None)
    return {"success": True, "prev_state": prev} if prev else {"success": False}


@router.get("/status")
async def get_status():
    resumen: Dict[str, int] = {}
    for st in conversaciones_estado.values():
        resumen[st] = resumen.get(st, 0) + 1
    return {"total": len(conversaciones_estado), "detalle": resumen}


@router.post("/send")
async def manual_send(numero: str, mensaje: str, opciones: List[str] | None = None):
    return (
        await ws.send_list(numero, mensaje, opciones)
        if opciones else await ws.send_text(numero, mensaje)
    )
