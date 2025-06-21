import httpx
import logging
import re
import json
from typing import List, Optional, Dict, Any, Union
from app.core.config import settings

logger = logging.getLogger(__name__)

async def enviar_mensaje_whatsapp(
    numero_destino: str, 
    mensaje: str, 
    opciones: Optional[List[str]] = None,
    tipo_mensaje: str = "normal"  # "normal", "confirmacion", "opciones", "lista"
) -> Dict:
    """Envía un mensaje por WhatsApp usando la API de Whapi."""
    try:
        # Normalizar número
        if '@' in numero_destino:
            numero_destino = numero_destino.split('@')[0]
        numero_destino = re.sub(r'[^0-9]', '', numero_destino)
        
        logger.info(f"Enviando mensaje a {numero_destino}")
        
        headers = {
            "Authorization": f"Bearer {settings.WHAPI_TOKEN}",
            "Content-Type": "application/json"
        }
        
        url = f"{settings.WHAPI_API_URL}/messages/interactive"
        
        if tipo_mensaje == "confirmacion":
            # Mensaje con botones Sí/No
            payload = {
                "to": numero_destino,
                "type": "button",
                "header": {
                    "text": "Encuesta"
                },
                "body": {
                    "text": mensaje
                },
                "footer": {
                    "text": "Por favor confirma para continuar"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "quick_reply",
                            "title": "Sí",
                            "id": "btn_si"
                        },
                        {
                            "type": "quick_reply", 
                            "title": "No",
                            "id": "btn_no"
                        }
                    ]
                }
            }
        elif tipo_mensaje == "lista" and opciones:
            # Mensaje con lista de opciones
            payload = {
                "to": numero_destino,
                "type": "list",
                "header": {
                    "text": "Opciones"
                },
                "body": {
                    "text": mensaje
                },
                "footer": {
                    "text": "Selecciona una opción"
                },
                "action": {
                    "list": {
                        "sections": [
                            {
                                "title": "Opciones disponibles",
                                "rows": [
                                    {
                                        "id": f"opt_{i}",
                                        "title": opcion[:24]  # Límite de WhatsApp
                                    } for i, opcion in enumerate(opciones)
                                ]
                            }
                        ],
                        "label": "Ver opciones"
                    }
                }
            }
        else:
            # Mensaje de texto normal
            url = f"{settings.WHAPI_API_URL}/messages/text"
            payload = {
                "to": numero_destino,
                "body": mensaje
            }

        logger.debug(f"Enviando payload: {json.dumps(payload, indent=2)}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Error: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
            
            return {"success": True, "response": response.json()}
            
    except Exception as e:
        logger.exception(f"Error enviando mensaje: {str(e)}")
        return {"success": False, "error": str(e)}


async def procesar_webhook_whatsapp(payload: Dict) -> Dict:
    """
    Procesa un webhook recibido de Whapi y extrae la información relevante.
    
    Args:
        payload: Payload completo del webhook
    
    Returns:
        Dict con información estructurada del mensaje
    """
    try:
        # Verificar si es un mensaje de estado
        if "statuses" in payload:
            return {
                "tipo": "estado",
                "detalles": payload.get("statuses", [{}])[0] if payload.get("statuses") else {}
            }
            
        # Verificar si es un mensaje
        if "messages" not in payload or not payload["messages"]:
            return {"tipo": "desconocido", "detalles": {}}
            
        mensaje = payload["messages"][0]
        
        # Si es un mensaje enviado por nosotros mismos
        if mensaje.get("from_me", False):
            return {"tipo": "propio", "detalles": mensaje}
        
        # Si no es un mensaje de texto
        if mensaje.get("type") != "text":
            return {
                "tipo": "no_texto",
                "subtipo": mensaje.get("type", "desconocido"),
                "detalles": mensaje
            }
        
        # Es un mensaje de texto válido
        numero = mensaje.get("from", "").split("@")[0] if "@" in mensaje.get("from", "") else mensaje.get("from", "")
        texto = mensaje.get("text", {}).get("body", "")
        
        return {
            "tipo": "mensaje",
            "numero": numero,
            "texto": texto,
            "mensaje_id": mensaje.get("id"),
            "timestamp": mensaje.get("timestamp"),
            "detalles": mensaje
        }
        
    except Exception as e:
        logger.exception(f"Error procesando webhook: {str(e)}")
        return {"tipo": "error", "error": str(e)}