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
    telefono_limpio = telefono.replace("+", "").replace(" ", "")
    if not telefono_limpio.isdigit():
        raise ValueError(f"Formato de teléfono inválido: {telefono}")

    preguntas_vapi = []
    for idx, pregunta in enumerate(preguntas):
        pregunta_vapi = {
            "id": str(pregunta["id"]),
            "texto": pregunta["texto"],
            "tipo": pregunta["tipo_pregunta_id"],
            "orden": idx + 1
        }
        if "opciones" in pregunta and pregunta["opciones"]:
            pregunta_vapi["opciones"] = [
                {"id": str(op["id"]), "texto": op["texto"]}
                for op in pregunta["opciones"]
            ]
        preguntas_vapi.append(pregunta_vapi)

    try:
        client = Vapi(token=settings.VAPI_API_KEY)

        response = client.calls.create(
            phone_number_id=settings.VAPI_PHONE_NUMBER_ID,
            assistant_id=settings.VAPI_ASSISTANT_ID,
            customer={
                "number": f"+{telefono_limpio}",
                "name": nombre_destinatario
            },
            metadata={
                "entrega_id": entrega_id,
                "campana": campana_nombre,
                "preguntas": preguntas_vapi
            },
            webhook_url=f"{settings.API_BASE_URL}/vapi/webhook"
        )

        return {
            "call_id": response.id,
            "status": response.status
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando llamada con Vapi: {str(e)}"
        )
