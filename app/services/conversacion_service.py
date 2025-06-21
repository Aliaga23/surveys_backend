# app/services/conversacion_service.py
from __future__ import annotations

import json, logging, re, unicodedata
from datetime import datetime
from typing import Any, Dict, List, Tuple
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.survey import (
    CampanaEncuesta,
    ConversacionEncuesta,
    EntregaEncuesta,
    PlantillaEncuesta,
    PreguntaEncuesta,
    RespuestaEncuesta,
    RespuestaPregunta,
)
from app.services.entregas_service import mark_as_responded  # ⬅️ NUEVO
from app.services.respuestas_service import crear_respuesta_encuesta
from app.services.shared_service import get_entrega_con_plantilla

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# --------------------------------------------------------------------------- #
# UTILIDADES
# --------------------------------------------------------------------------- #


def _norm(txt: str) -> str:
    """minúsculas, sin acentos, espacios colapsados → para comparación rápida"""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt.lower().strip())


# --------------------------------------------------------------------------- #
# DESAMBIGUAR OPCIONES
# --------------------------------------------------------------------------- #
# ---------- helper _match_opcion_ai (usa GPT SOLO en múltiple) ----------- #

async def _match_opcion_ai(
    respuesta: str,
    opciones: List[str],
    multiple: bool,
) -> Tuple[Any, str]:
    """
    • Pregunta de opción única (tipo 3)  →
        1) Intenta coincidencia exacta o número “1-based”.
        2) Si no encuentra nada, pregunta a GPT (fallback).
    • Pregunta multiselección (tipo 4)  →
        Siempre delega a GPT; no hace ningún match local.
    Devuelve:
        – int          (para tipo 3)
        – List[int]    (para tipo 4)
        – (None, msg)  si no reconoce la respuesta.
    """

    # ---------- opción ÚNICA : intentamos match directo ------------------ #
    if not multiple:
        n_resp = _norm(respuesta)

        # 1) texto exacto
        for i, op in enumerate(opciones):
            if n_resp == _norm(op):
                return i, ""

        # 2) algún número “1-based” dentro del mensaje
        for n in [int(x) - 1 for x in re.findall(r"\b\d+\b", respuesta)]:
            if 0 <= n < len(opciones):
                return n, ""
        # …si falló, se cae a GPT como fallback

    # -------------------- GPT (multiselección o fallback) ---------------- #
    prompt = (
        "Lista de opciones con su índice (0-based):\n"
        + "\n".join(f"[{i}] {o}" for i, o in enumerate(opciones))
        + "\n\nRespuesta del usuario:\n"
        + respuesta
        + "\n\nDevuelve *solo* los índices "
        + ("separados por coma" if multiple else "")
        + ". Si no reconoces nada responde exactamente 'ERROR'."
    )

    try:
        rsp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        txt = rsp.choices[0].message.content.strip()

        if txt.upper().startswith("ERROR"):
            return None, (
                "No pude identificar tu selección. "
                "Por favor elige una opción válida de la lista."
            )

        idxs = [int(n) for n in re.findall(r"\d+", txt)]

        if multiple:
            buenos = [i for i in idxs if 0 <= i < len(opciones)]
            if buenos:
                return buenos, ""
            return None, (
                "No reconozco ninguna de las opciones que escribiste. "
                "Intenta nuevamente."
            )
        else:  # único, llegó aquí solo como fallback
            if idxs and 0 <= idxs[0] < len(opciones):
                return idxs[0], ""
            return None, (
                "No reconozco la opción que escribiste. "
                "Intenta nuevamente."
            )

    except Exception as exc:  # pragma: no cover
        logger.debug("GPT error: %s", exc)
        return None, (
            "Ocurrió un problema interpretando tu respuesta. "
            "Intenta nuevamente."
        )



# --------------------------------------------------------------------------- #
# FUNCIÓN PRINCIPAL
# --------------------------------------------------------------------------- #


async def procesar_respuesta(
    db: Session,
    conversacion_id: UUID,
    respuesta: str,
) -> Dict[str, Any]:
    # -------- contexto ---------------------------------------------------- #
    conv = (
        db.query(ConversacionEncuesta)
        .options(
            joinedload(ConversacionEncuesta.entrega)
            .joinedload(EntregaEncuesta.campana)
            .joinedload(CampanaEncuesta.plantilla)
        )
        .filter(ConversacionEncuesta.id == conversacion_id)
        .first()
    )
    if not conv:
        raise ValueError("Conversación no encontrada")
    if conv.completada:
        return {"completada": True}

    # -------- historial --------------------------------------------------- #
    conv.historial = conv.historial or []
    conv.historial.append(
        {
            "role": "user",
            "content": respuesta,
            "timestamp": datetime.now().isoformat(),
        }
    )

    # -------- pregunta actual -------------------------------------------- #
    pregunta = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.id == conv.pregunta_actual_id)
        .first()
    )
    if not pregunta:
        raise ValueError("Pregunta actual no encontrada")

    # -------- validar ----------------------------------------------------- #
    if pregunta.tipo_pregunta_id == 1:  # texto libre
        valor = respuesta

    elif pregunta.tipo_pregunta_id == 2:  # numérico
        try:
            valor = float(respuesta.strip())
        except ValueError:
            return {"error": "Por favor ingresa un número válido."}

    else:  # opciones
        valor, err = await _match_opcion_ai(
            respuesta,
            [o.texto for o in pregunta.opciones],
            multiple=(pregunta.tipo_pregunta_id == 4),
        )
        if err:
            return {"error": err}

    # --------------------------------------------------------------------- #
    #  GUARDAR RESPUESTA EN BD
    # --------------------------------------------------------------------- #
    r_enc = (
        db.query(RespuestaEncuesta)
        .filter(RespuestaEncuesta.entrega_id == conv.entrega_id)
        .first()
    )
    if not r_enc:
        r_enc = RespuestaEncuesta(entrega_id=conv.entrega_id)
        db.add(r_enc)
        db.commit()
        db.refresh(r_enc)

    if pregunta.tipo_pregunta_id == 1:
        det = RespuestaPregunta(
            respuesta_id=r_enc.id,
            pregunta_id=pregunta.id,
            texto=valor,
        )
    elif pregunta.tipo_pregunta_id == 2:
        det = RespuestaPregunta(
            respuesta_id=r_enc.id,
            pregunta_id=pregunta.id,
            numero=valor,
        )
    elif pregunta.tipo_pregunta_id == 3:
        det = RespuestaPregunta(
            respuesta_id=r_enc.id,
            pregunta_id=pregunta.id,
            opcion_id=pregunta.opciones[valor].id,  # type: ignore[arg-type]
        )
    else:  # multiselección
        uuids = [str(pregunta.opciones[i].id) for i in valor]  # type: ignore[arg-type]
        det = RespuestaPregunta(
            respuesta_id=r_enc.id,
            pregunta_id=pregunta.id,
            metadatos={"opciones": uuids},
        )

    db.add(det)
    db.commit()

    # --------------------------------------------------------------------- #
    #  SIGUIENTE PREGUNTA
    # --------------------------------------------------------------------- #
    todas = (
        db.query(PreguntaEncuesta)
        .join(PlantillaEncuesta)
        .join(CampanaEncuesta)
        .join(EntregaEncuesta)
        .filter(EntregaEncuesta.id == conv.entrega_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )
    pos = {p.id: i for i, p in enumerate(todas)}[pregunta.id]
    siguiente = todas[pos + 1] if pos + 1 < len(todas) else None

    # ---------- fin de encuesta ------------------------------------------ #
    if not siguiente:
        conv.completada = True
        db.commit()

        # marcar la entrega como RESPONDIDA (estado 3)
        mark_as_responded(db, conv.entrega_id)

        resumen = await crear_respuesta_encuesta(
            db, conv.entrega_id, conv.historial
        )
        return {"completada": True, "respuesta_id": str(resumen.id)}

    # ---------- avanzar puntero ------------------------------------------ #
    conv.pregunta_actual_id = siguiente.id
    db.commit()

    salida: Dict[str, Any] = {
        "completada": False,
        "siguiente_pregunta": siguiente.texto,
        "tipo_pregunta": siguiente.tipo_pregunta_id,
    }
    if siguiente.tipo_pregunta_id in (3, 4):
        salida["opciones"] = [o.texto for o in siguiente.opciones]
    return salida


# --------------------------------------------------------------------------- #
# CREAR CONVERSACIÓN INICIAL
# --------------------------------------------------------------------------- #


async def iniciar_conversacion_whatsapp(
    db: Session,
    entrega_id: UUID,
) -> ConversacionEncuesta:
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega or not entrega.destinatario.telefono:
        raise ValueError("Entrega no válida o sin teléfono")

    primera = (
        db.query(PreguntaEncuesta)
        .join(PlantillaEncuesta)
        .join(CampanaEncuesta)
        .join(EntregaEncuesta)
        .filter(EntregaEncuesta.id == entrega_id)
        .order_by(PreguntaEncuesta.orden)
        .first()
    )
    if not primera:
        raise ValueError("La plantilla no tiene preguntas")

    conv = ConversacionEncuesta(
        entrega_id=entrega_id,
        completada=False,
        historial=[],
        pregunta_actual_id=primera.id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv
