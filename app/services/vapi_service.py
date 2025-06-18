import httpx
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
    """
    # Normalizar el teléfono (quitar +, espacios, etc.)
    telefono_limpio = telefono.replace("+", "").replace(" ", "")
    if not telefono_limpio.isdigit():
        raise ValueError(f"Formato de teléfono inválido: {telefono}")
    
    # Formatear las preguntas para el formato de Vapi
    preguntas_vapi = []
    for idx, pregunta in enumerate(preguntas):
        pregunta_vapi = {
            "id": str(pregunta["id"]),
            "texto": pregunta["texto"],
            "tipo": pregunta["tipo_pregunta_id"],
            "orden": idx + 1
        }
        
        # Añadir opciones si existen
        if "opciones" in pregunta and pregunta["opciones"]:
            pregunta_vapi["opciones"] = [
                {"id": str(op["id"]), "texto": op["texto"]} 
                for op in pregunta["opciones"]
            ]
            
        preguntas_vapi.append(pregunta_vapi)
    
    # Construir el payload para Vapi
    payload = {
        "destinatario": {
            "telefono": telefono_limpio,
            "nombre": nombre_destinatario
        },
        "encuesta": {
            "nombre": campana_nombre,
            "preguntas": preguntas_vapi
        },
        "callback_url": f"{settings.API_BASE_URL}/vapi/webhook",
        "entrega_id": str(entrega_id)
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.VAPI_API_URL}/calls",
                headers={
                    "Authorization": f"Bearer {settings.VAPI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=10.0
            )
            
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando llamada con Vapi: {str(e)}"
        )