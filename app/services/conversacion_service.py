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
from app.services.respuestas_service import crear_respuesta_encuesta
from app.services.shared_service import get_entrega_con_plantilla

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def _norm(txt: str) -> str:
    """Devuelve el texto normalizado (minúsculas, sin acentos, espacios colapsados)."""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt.lower().strip())


async def _match_opcion_ai(
    respuesta: str, opciones: List[str], multiple: bool
) -> Tuple[Any, str]:
    """
    Para tipo 3 (única) → índice (int)
    Para tipo 4 (multi)  → lista[int]
    Devuelve (None, msg_error) si no pudo.
    """
    norm_resp = _norm(respuesta)
    norm_opts = [_norm(o) for o in opciones]
    indices: List[int] = []

    # 1. Coincidencias explícitas de texto
    for i, opt in enumerate(norm_opts):
        if opt and opt in norm_resp:
            indices.append(i)

    # 2. Coincidencias por número 1-basado
    nums = [int(n) - 1 for n in re.findall(r"\b\d+\b", respuesta)]
    indices.extend([n for n in nums if 0 <= n < len(opciones)])
    indices = sorted(set(indices))

    if indices:
        return (indices if multiple else indices[0]), ""

    # 3. Fallback GPT
    prompt = (
        f"Opciones: {', '.join(opciones)}\n"
        f"Respuesta: {respuesta}\n"
        f"Devuelve {'índices separados por coma' if multiple else 'un índice numérico'} "
        f"o 'ERROR' si no se entiende."
    )
    try:
        rsp = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        txt = rsp.choices[0].message.content.strip()
        if txt.upper().startswith("ERROR"):
            return None, "No pude identificar tu selección. Elige exactamente de la lista."

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
# Principales
# --------------------------------------------------------------------------- #

async def procesar_respuesta(
    db: Session, conversacion_id: UUID, respuesta: str
) -> Dict[str, Any]:
    # ---------- cargar objetos ----------
    conv: ConversacionEncuesta | None = (
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

    # ---------- añadir al historial ----------
    conv.historial = conv.historial or []
    conv.historial.append(
        {"role": "user", "content": respuesta, "timestamp": datetime.now().isoformat()}
    )

    # ---------- pregunta actual ----------
    pregunta: PreguntaEncuesta | None = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.id == conv.pregunta_actual_id)
        .first()
    )
    if not pregunta:
        raise ValueError("Pregunta actual no encontrada")

    # ---------- validar respuesta ----------
    if pregunta.tipo_pregunta_id == 1:  # texto
        valor = respuesta

    elif pregunta.tipo_pregunta_id == 2:  # número
        try:
            valor = float(respuesta.strip())
        except ValueError:
            return {"error": "Por favor ingresa un número válido."}

    else:  # opciones (3 o 4)
        opts = [o.texto for o in pregunta.opciones]
        idxs, err = await _match_opcion_ai(
            respuesta, opts, multiple=(pregunta.tipo_pregunta_id == 4)
        )
        if err:
            listado = "\n".join(f"• {t}" for t in opts)
            return {"error": f"{err}\nOpciones disponibles:\n{listado}"}
        valor = idxs

    # ---------------------------------------------------------------------- #
    #  GUARDAR RESPUESTA EN BD
    # ---------------------------------------------------------------------- #
    r_enc: RespuestaEncuesta | None = (
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
            respuesta_id=r_enc.id, pregunta_id=pregunta.id, texto=valor
        )
    elif pregunta.tipo_pregunta_id == 2:
        det = RespuestaPregunta(
            respuesta_id=r_enc.id, pregunta_id=pregunta.id, numero=valor
        )
    elif pregunta.tipo_pregunta_id == 3:
        det = RespuestaPregunta(
            respuesta_id=r_enc.id,
            pregunta_id=pregunta.id,
            opcion_id=pregunta.opciones[valor].id,  # type: ignore[arg-type]
        )
    else:  # multisel
        ids = [str(pregunta.opciones[i].id) for i in valor]  # type: ignore[arg-type]
        det = RespuestaPregunta(
            respuesta_id=r_enc.id, pregunta_id=pregunta.id, metadatos={"opciones": ids}
        )

    db.add(det)
    db.commit()

    # ---------------------------------------------------------------------- #
    #  Siguiente pregunta
    # ---------------------------------------------------------------------- #
    todas: List[PreguntaEncuesta] = (
        db.query(PreguntaEncuesta)
        .join(PlantillaEncuesta)
        .join(CampanaEncuesta)
        .join(EntregaEncuesta)
        .filter(EntregaEncuesta.id == conv.entrega_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )
    idx_actual = {p.id: i for i, p in enumerate(todas)}[pregunta.id]
    siguiente = todas[idx_actual + 1] if idx_actual + 1 < len(todas) else None

    # ------------------------------------------------------------------ fin
    if not siguiente:
        conv.completada = True
        # marcar entrega como respondida
        entrega = conv.entrega
        entrega.estado_id = 3  # respondido
        entrega.respondido_en = datetime.utcnow()
        db.commit()

        resumen = await crear_respuesta_encuesta(db, conv.entrega_id, conv.historial)
        return {"completada": True, "respuesta_id": str(resumen.id)}

    # actualizar puntero y continuar
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
#  Crear conversación inicial (para el router)
# --------------------------------------------------------------------------- #

async def iniciar_conversacion_whatsapp(
    db: Session, entrega_id: UUID
) -> ConversacionEncuesta:
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega or not entrega.destinatario.telefono:
        raise ValueError("Entrega no válida o sin teléfono")

    primera: PreguntaEncuesta | None = (
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
