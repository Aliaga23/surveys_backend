from __future__ import annotations
from typing import List, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime
import re, json, logging

from sqlalchemy.orm import Session, joinedload
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.survey import (
    CampanaEncuesta, ConversacionEncuesta, EntregaEncuesta,
    PlantillaEncuesta, PreguntaEncuesta
)
from app.services.shared_service import get_entrega_con_plantilla
from app.services.respuestas_service import crear_respuesta_encuesta

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# --------------------------------------------------------------------------- #
# UTILIDADES GPT (opcional, las mantengo porque ya las usas)
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """
Eres un asistente amigable realizando una encuesta. Tu objetivo es obtener
respuestas para las preguntas de la encuesta de manera natural y conversacional.
"""

async def generar_siguiente_pregunta(
    historial: List[Dict], texto: str, tipo: int
) -> str:
    msg = [{"role": "system", "content": SYSTEM_PROMPT}]
    msg += [m for m in historial if m.get("role") and m.get("content")]
    contexto = {
        1: "Pregunta abierta.",
        2: "Pregunta numérica.",
        3: "Pregunta de opción única: dile que elija exactamente una de la lista.",
        4: "Pregunta multiselección: puede elegir varias separadas por coma."
    }
    msg.append({
        "role": "system",
        "content": f"Debes preguntar: '{texto}'. {contexto.get(tipo, '')}"
    })
    rsp = await client.chat.completions.create(
        model="gpt-3.5-turbo", messages=msg, temperature=0.3
    )
    return rsp.choices[0].message.content.strip()

# --------------------------------------------------------------------------- #
#  ANALÍTICA DE RESPUESTAS (recortado a lo esencial)
# --------------------------------------------------------------------------- #

async def _match_opcion_ai(
    respuesta: str, opciones: List[str], multiple: bool
) -> Tuple[Any, str]:
    """
    Devuelve el/los índice(s) seleccionados o (None, error_msg)
    multiple = False → tipo 3   |  multiple = True → tipo 4
    """
    # Intento de coincidencia exacta
    if not multiple:
        for i, op in enumerate(opciones):
            if respuesta.strip().lower() == op.lower():
                return i, ""
    else:
        exactos = []
        for trozo in [t.strip().lower() for t in respuesta.split(",")]:
            for i, op in enumerate(opciones):
                if trozo == op.lower():
                    exactos.append(i)
        if exactos:
            return exactos, ""

    # Si falla coincidencia exacta, consultamos GPT rápido
    prompt = (
        f"Opciones: {', '.join(opciones)}\n"
        f"Respuesta: {respuesta}\n"
        f"Devuelve sólo índices {'separados por coma' if multiple else 'numérico'} "
        f"o 'ERROR' si no se entiende."
    )
    rsp = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    txt = rsp.choices[0].message.content.strip()
    if txt.upper().startswith("ERROR"):
        return None, "No pude identificar tu selección. Elige exactamente de la lista."
    try:
        idx = [int(n) for n in re.findall(r"\d+", txt)]
        if not multiple:
            if idx and 0 <= idx[0] < len(opciones):
                return idx[0], ""
        else:
            buenos = [i for i in idx if 0 <= i < len(opciones)]
            if buenos:
                return buenos, ""
        return None, "La opción seleccionada no es válida."
    except Exception as e:
        logger.debug("GPT parse error: %s", e)
        return None, "No pude identificar tu selección."

# --------------------------------------------------------------------------- #
#  FUNCIÓN PRINCIPAL
# --------------------------------------------------------------------------- #

async def procesar_respuesta(
    db: Session, conversacion_id: UUID, respuesta: str
) -> Dict[str, Any]:
    """
    Procesa la respuesta del usuario y decide el siguiente paso.
    Devuelve un dict uniforme (ver descripción arriba).
    """
    conv = (
        db.query(ConversacionEncuesta)
        .options(joinedload(ConversacionEncuesta.entrega)
                 .joinedload(EntregaEncuesta.campana)
                 .joinedload(CampanaEncuesta.plantilla))
        .filter(ConversacionEncuesta.id == conversacion_id)
        .first()
    )
    if not conv:
        raise ValueError("Conversación no encontrada")

    if conv.completada:
        return {"completada": True}

    # ---------- agregar al historial ----------
    conv.historial = conv.historial or []
    conv.historial.append({
        "role": "user",
        "content": respuesta,
        "timestamp": datetime.now().isoformat()
    })

    # ---------- pregunta actual ----------
    pregunta = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.id == conv.pregunta_actual_id)
        .first()
    )
    if not pregunta:
        raise ValueError("Pregunta actual no encontrada")

    # ---------- validar respuesta ----------
    valor: Any = None
    if pregunta.tipo_pregunta_id == 1:           # texto libre
        valor = respuesta

    elif pregunta.tipo_pregunta_id == 2:         # numérico
        try:
            valor = float(respuesta.strip())
        except ValueError:
            return {"error": "Por favor ingresa un número válido."}

    elif pregunta.tipo_pregunta_id in (3, 4):    # opciones
        ops = [o.texto for o in pregunta.opciones]
        idxs, err = await _match_opcion_ai(
            respuesta, ops, multiple=(pregunta.tipo_pregunta_id == 4)
        )
        if err:
            listado = "\n".join(f"• {t}" for t in ops)
            return {"error": f"{err}\nOpciones disponibles:\n{listado}"}
        valor = idxs

    # TODO: guardar valor_procesado en la tabla de respuestas si procede
    # (omito el detalle para enfocarnos en el flujo)

    # ---------- decidir siguiente pregunta ----------
    todas = (
        db.query(PreguntaEncuesta)
        .join(PlantillaEncuesta)
        .join(CampanaEncuesta)
        .join(EntregaEncuesta)
        .filter(EntregaEncuesta.id == conv.entrega_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )
    siguiente = None
    for idx, q in enumerate(todas):
        if q.id == pregunta.id and idx + 1 < len(todas):
            siguiente = todas[idx + 1]
            break

    if not siguiente:   # terminó la encuesta
        conv.completada = True
        db.commit()
        resp = await crear_respuesta_encuesta(db, conv.entrega_id, conv.historial)
        return {
            "completada": True,
            "respuesta_id": str(resp.id)
        }

    # actualizar puntero y commit
    conv.pregunta_actual_id = siguiente.id
    db.commit()

    # preparar salida uniforme
    salida = {
        "completada": False,
        "siguiente_pregunta": siguiente.texto,
        "tipo_pregunta": siguiente.tipo_pregunta_id,
    }
    if siguiente.tipo_pregunta_id in (3, 4):
        salida["opciones"] = [o.texto for o in siguiente.opciones]
    return salida

# --------------------------------------------------------------------------- #
#  INICIAR CONVERSACIÓN (ya lo movimos aquí para uso global)
# --------------------------------------------------------------------------- #

async def iniciar_conversacion_whatsapp(db: Session, entrega_id: UUID) -> ConversacionEncuesta:
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega or not entrega.destinatario.telefono:
        raise ValueError("Entrega no válida o sin teléfono")

    primera = (
        db.query(PreguntaEncuesta)
        .join(PlantillaEncuesta).join(CampanaEncuesta)
        .join(EntregaEncuesta)
        .filter(EntregaEncuesta.id == entrega_id)
        .order_by(PreguntaEncuesta.orden).first()
    )
    if not primera:
        raise ValueError("La plantilla no tiene preguntas")

    conv = ConversacionEncuesta(
        entrega_id=entrega_id,
        completada=False,
        historial=[],
        pregunta_actual_id=primera.id
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv
