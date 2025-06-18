from vapi import Vapi
from typing import List, Dict, Any
from fastapi import HTTPException, status
from app.core.config import settings


async def crear_llamada_encuesta(
    telefono: str,
    nombre_destinatario: str,
    campana_nombre: str,
    preguntas: List[Dict[str, Any]],
    entrega_id: str
):
    """Lanza una llamada de encuesta usando vapi-server-sdk."""
    # ── Normaliza teléfono ───────────────────────────────────────────────
    telefono_limpio = telefono.replace("+", "").replace(" ", "")
    if not telefono_limpio.isdigit():
        raise ValueError(f"Formato de teléfono inválido: {telefono}")

    # ── Prepara preguntas para auditoría / debugging ─────────────────────
    preguntas_vapi: list[dict[str, Any]] = []
    for idx, p in enumerate(preguntas):
        data = {
            "id": str(p["id"]),
            "texto": p["texto"],
            "tipo": p["tipo_pregunta_id"],
            "orden": idx + 1,
        }
        if p.get("opciones"):
            data["opciones"] = [
                {"id": str(o["id"]), "texto": o["texto"]} for o in p["opciones"]
            ]
        preguntas_vapi.append(data)

    # ── Llama a la API de Vapi ───────────────────────────────────────────
    try:
        client = Vapi(token=settings.VAPI_API_KEY)

        response = client.calls.create(
            phone_number_id=settings.VAPI_PHONE_NUMBER_ID,
            assistant_id=settings.VAPI_ASSISTANT_ID,
            customer={
                "number": f"+{telefono_limpio}",
                "name": nombre_destinatario,
                "customData": {
                    "entrega_id": entrega_id,
                    "campana": campana_nombre,
                    "preguntas": preguntas_vapi,
                },
            },
        )

        return {"call_id": response.id, "status": response.status}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando llamada con Vapi: {e}",
        )
