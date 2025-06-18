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
    """
    Crea una llamada con Vapi para realizar una encuesta telefónica
    usando el SDK oficial de Vapi Server (vapi_server_sdk).
    """
    # 1. Normaliza el teléfono
    telefono_limpio = telefono.replace("+", "").replace(" ", "")
    if not telefono_limpio.isdigit():
        raise ValueError(f"Formato de teléfono inválido: {telefono}")

    # 2. Prepara el payload de preguntas
    preguntas_vapi: list[dict[str, Any]] = []
    for idx, pregunta in enumerate(preguntas):
        pregunta_vapi = {
            "id": str(pregunta["id"]),
            "texto": pregunta["texto"],
            "tipo": pregunta["tipo_pregunta_id"],
            "orden": idx + 1
        }
        if pregunta.get("opciones"):
            pregunta_vapi["opciones"] = [
                {"id": str(op["id"]), "texto": op["texto"]}
                for op in pregunta["opciones"]
            ]
        preguntas_vapi.append(pregunta_vapi)

    try:
        # 3. Instancia del cliente
        client = Vapi(token=settings.VAPI_API_KEY)

        # 4. Crea la llamada
        response = client.calls.create(
            phone_number_id=settings.VAPI_PHONE_NUMBER_ID,
            assistant_id=settings.VAPI_ASSISTANT_ID,
            customer={
                "number": f"+{telefono_limpio}",
                "name": nombre_destinatario,
                "customData": {                 # 👈 Aquí viajan tus metadatos
                    "entrega_id": entrega_id,
                    "campana": campana_nombre,
                    "preguntas": preguntas_vapi
                }
            },
            webhook_url=f"{settings.API_BASE_URL}/vapi/webhook"
        )

        # 5. Devuelve información relevante
        return {
            "call_id": response.id,
            "status": response.status
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando llamada con Vapi: {e}"
        )
