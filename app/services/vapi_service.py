# app/services/vapi_service.py
from __future__ import annotations

from typing import List, Dict, Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from vapi import Vapi

from app.core.config import settings
from app.models.survey import VapiCallRelation



# ──────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
async def crear_llamada_encuesta(
    db: Session,
    entrega_id: UUID,
    telefono: str,
    nombre_destinatario: str,
    campana_nombre: str,
    preguntas: List[Dict[str, Any]],
):
    """
    Lanza una llamada de encuesta con Vapi y registra la relación call_id → entrega_id.

    - **db**: sesión SQLAlchemy
    - **entrega_id**: FK a entrega_encuesta
    - **telefono**: número del destinatario (código país incluido)
    - **nombre_destinatario**: para personalizar el saludo
    - **campana_nombre**: nombre visible de la campaña
    - **preguntas**: lista de dicts con la estructura:
        {
          "id": str(uuid),
          "texto": str,
          "tipo_pregunta_id": int,
          "opciones": [ {"id": str(uuid), "texto": str}, ... ]
        }
    """
    # 1. Cliente Vapi
    client = Vapi(token=settings.VAPI_API_KEY)

    # 2. Teléfono en formato E.164 (+591…)
    telefono_e164 = telefono.replace(" ", "")
    if not telefono_e164.startswith("+"):
        telefono_e164 = f"+{telefono_e164}"

    # 3. Construir prompt/contexto dinámico
    contexto = (
        "Eres un asistente profesional realizando una encuesta telefónica.\n\n"
        "Tu objetivo es obtener respuestas claras a las siguientes preguntas:\n\n"
    )

    for idx, p in enumerate(preguntas, start=1):
        contexto += f"Pregunta {idx}: {p['texto']}\n"
        if p.get("opciones"):
            contexto += "Opciones:\n"
            for j, op in enumerate(p["opciones"]):
                letra = chr(65 + j)
                contexto += f"  {letra}) {op['texto']}\n"
        contexto += "\n"

    # 4. JSON Schema para análisis estructurado
    schema = {
        "type": "object",
        "properties": {
            "puntuacion": {"type": "number"},
            "respuestas_preguntas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pregunta_id": {"type": "string"},
                        "tipo_pregunta_id": {"type": "integer"},
                        "texto": {"type": "string"},
                        "numero": {"type": "number"},
                        "opcion_id": {"type": "string"},
                    },
                    "required": ["pregunta_id", "tipo_pregunta_id"],
                },
            },
        },
        "required": ["respuestas_preguntas"],
    }

    # 5. Assistant transitorio
    assistant = {
        "firstMessage": (
            "Hola {{nombre}}, soy un asistente realizando una encuesta "
            "sobre {{campana}}. ¿Tienes unos minutos?"
        ),
        "context": contexto,
        "analysisPlan": {"structuredDataSchema": schema},
        "voice": "juan-rime-ai" # Voz por defecto
        # Omitimos voice y model para usar los valores por defecto
    }

    try:
        # 6. Crear la llamada
        call = client.calls.create(
            phone_number_id=settings.VAPI_PHONE_NUMBER_ID,
            assistant=assistant,
            customer={
                "number": telefono_e164,
                "name": nombre_destinatario,
            },
            assistant_overrides={
                "variableValues": {
                    "nombre": nombre_destinatario,
                    "campana": campana_nombre,
                }
            },
        )

        # 7. Persistir relación call_id ↔ entrega_id
        db.add(VapiCallRelation(entrega_id=entrega_id, call_id=call.id))
        db.commit()

        return {"call_id": call.id, "status": call.status}

    except Exception as exc:
        # Rollback por si falla antes del commit
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando llamada con Vapi: {exc}",
        ) from exc



