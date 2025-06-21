from __future__ import annotations
from typing import List, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime
import re, json, logging, unicodedata  # <- unicodedata para _norm

from sqlalchemy.orm import Session, joinedload
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.survey import (
    CampanaEncuesta, ConversacionEncuesta, EntregaEncuesta,
    PlantillaEncuesta, PreguntaEncuesta,
    RespuestaEncuesta, RespuestaPregunta
)
from app.services.shared_service import get_entrega_con_plantilla
from app.services.respuestas_service import crear_respuesta_encuesta

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# --------------------------------------------------------------------------- #
# UTILIDADES
# --------------------------------------------------------------------------- #

def _norm(txt: str) -> str:
    """Minúsculas, sin acentos, espacios colapsados → para comparación."""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r"\s+", " ", txt.lower().strip())
    return txt

SYSTEM_PROMPT = """
Eres un asistente amigable realizando una encuesta. Tu objetivo es obtener
respuestas para las preguntas de la encuesta de manera natural y conversacional.
"""

async def generar_siguiente_pregunta(
    historial: List[Dict], texto: str, tipo: int
) -> str:
    # (se mantiene por si quieres usarlo desde otro módulo)
    msg = [{"role": "system", "content": SYSTEM_PROMPT}]
    msg += [m for m in historial if m.get("role") and m.get("content")]
    contexto = {
        1: "Pregunta abierta.",
        2: "Pregunta numérica.",
        3: "Pregunta de opción única: pide elegir exactamente una de la lista.",
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
#  Desambiguar opciones (exact-match normalizado  →  GPT fallback)
# --------------------------------------------------------------------------- #

async def _match_opcion_ai(
    respuesta: str, opciones: List[str], multiple: bool
) -> Tuple[Any, str]:
    """
    Devuelve:
      • índice int  (tipo 3)
      • lista[int] (tipo 4)
      • (None, error_msg) si no se identifica
    """
    r_norm = _norm(respuesta)

    # --- Coincidencia exacta normalizada -----------------------------------
    if not multiple:
        for i, op in enumerate(opciones):
            if r_norm == _norm(op):
                return i, ""
    else:
        exactos: List[int] = []
        for trozo in [_norm(t) for t in respuesta.split(",")]:
            for i, op in enumerate(opciones):
                if trozo == _norm(op):
                    exactos.append(i)
        if exactos:
            return exactos, ""

    # --- GPT como último recurso ------------------------------------------
    prompt = (
        f"Opciones: {', '.join(opciones)}\n"
        f"Respuesta: {respuesta}\n"
        f"Devuelve {'índices separados por coma' if multiple else 'un índice numérico'} "
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
        nums = [int(n) for n in re.findall(r"\d+", txt)]
        if not multiple and nums and 0 <= nums[0] < len(opciones):
            return nums[0], ""
        if multiple:
            buenos = [i for i in nums if 0 <= i < len(opciones)]
            if buenos:
                return buenos, ""
        return None, "La opción seleccionada no es válida."
    except Exception as exc:
        logger.debug("GPT parse error: %s", exc)
        return None, "No pude identificar tu selección."

# --------------------------------------------------------------------------- #
#  FUNCIÓN PRINCIPAL
# --------------------------------------------------------------------------- #

async def procesar_respuesta(
    db: Session, conversacion_id: UUID, respuesta: str
) -> Dict[str, Any]:
    # --- cargar conversación + contexto ------------------------------------
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

    # --- añadir al historial ----------------------------------------------
    conv.historial = conv.historial or []
    conv.historial.append({
        "role": "user", "content": respuesta,
        "timestamp": datetime.now().isoformat()
    })

    # --- obtener pregunta actual ------------------------------------------
    pregunta = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.id == conv.pregunta_actual_id)
        .first()
    )
    if not pregunta:
        raise ValueError("Pregunta actual no encontrada")

    # --- validar y traducir respuesta -------------------------------------
    if pregunta.tipo_pregunta_id == 1:            # texto
        valor = respuesta
    elif pregunta.tipo_pregunta_id == 2:          # numérico
        try:
            valor = float(respuesta.strip())
        except ValueError:
            return {"error": "Por favor ingresa un número válido."}
    else:                                         # opciones
        opts = [o.texto for o in pregunta.opciones]
        idxs, err = await _match_opcion_ai(
            respuesta, opts,
            multiple=(pregunta.tipo_pregunta_id == 4)
        )
        if err:
            lista = "\n".join(f"• {t}" for t in opts)
            return {"error": f"{err}\nOpciones disponibles:\n{lista}"}
        valor = idxs

    # ---------------------------------------------------------------------- #
    #  GUARDAR RESPUESTA EN BD
    # ---------------------------------------------------------------------- #
    r_enc = (
        db.query(RespuestaEncuesta)
        .filter(RespuestaEncuesta.entrega_id == conv.entrega_id)
        .first()
    )
    if not r_enc:
        r_enc = RespuestaEncuesta(entrega_id=conv.entrega_id)
        db.add(r_enc); db.commit(); db.refresh(r_enc)

    if pregunta.tipo_pregunta_id == 1:
        detalle = RespuestaPregunta(
            respuesta_id=r_enc.id, pregunta_id=pregunta.id, texto=valor
        )
    elif pregunta.tipo_pregunta_id == 2:
        detalle = RespuestaPregunta(
            respuesta_id=r_enc.id, pregunta_id=pregunta.id, numero=valor
        )
    elif pregunta.tipo_pregunta_id == 3:
        opcion = pregunta.opciones[valor]
        detalle = RespuestaPregunta(
            respuesta_id=r_enc.id, pregunta_id=pregunta.id, opcion_id=opcion.id
        )
    else:   # multiselección
        ids = [pregunta.opciones[i].id for i in valor]
        detalle = RespuestaPregunta(
            respuesta_id=r_enc.id, pregunta_id=pregunta.id,
            metadatos={"opciones": ids}
        )
    db.add(detalle); db.commit()

    # ---------------------------------------------------------------------- #
    #  Seleccionar siguiente pregunta
    # ---------------------------------------------------------------------- #
    todas = (
        db.query(PreguntaEncuesta)
        .join(PlantillaEncuesta).join(CampanaEncuesta).join(EntregaEncuesta)
        .filter(EntregaEncuesta.id == conv.entrega_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )
    pos = {p.id: i for i, p in enumerate(todas)}[pregunta.id]
    siguiente = todas[pos + 1] if pos + 1 < len(todas) else None

    if not siguiente:                      # fin
        conv.completada = True; db.commit()
        resumen = await crear_respuesta_encuesta(
            db, conv.entrega_id, conv.historial
        )
        return {"completada": True, "respuesta_id": str(resumen.id)}

    conv.pregunta_actual_id = siguiente.id; db.commit()

    salida = {
        "completada": False,
        "siguiente_pregunta": siguiente.texto,
        "tipo_pregunta": siguiente.tipo_pregunta_id,
    }
    if siguiente.tipo_pregunta_id in (3, 4):
        salida["opciones"] = [o.texto for o in siguiente.opciones]
    return salida

# --------------------------------------------------------------------------- #
#  Crear conversación inicial
# --------------------------------------------------------------------------- #

async def iniciar_conversacion_whatsapp(
    db: Session, entrega_id: UUID
) -> ConversacionEncuesta:
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega or not entrega.destinatario.telefono:
        raise ValueError("Entrega no válida o sin teléfono")

    primera = (
        db.query(PreguntaEncuesta)
        .join(PlantillaEncuesta).join(CampanaEncuesta).join(EntregaEncuesta)
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
    db.add(conv); db.commit(); db.refresh(conv)
    return conv
