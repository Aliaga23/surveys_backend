import httpx
import logging
import re
import json
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

async def enviar_mensaje_whatsapp(
    numero_destino: str, 
    mensaje: str, 
    opciones: Optional[List[str]] = None
) -> Dict:
    """
    Envía un mensaje por WhatsApp usando la API de Whapi.
    """
    try:
        # Normalizar número de teléfono (eliminar @c.us si existe)
        if '@' in numero_destino:
            numero_destino = numero_destino.split('@')[0]
        
        # Eliminar espacios y caracteres especiales
        numero_destino = re.sub(r'[^0-9]', '', numero_destino)
        
        logger.info(f"Enviando mensaje a {numero_destino}: {mensaje[:50]}...")
        
        # Preparar headers comunes
        headers = {
            "Authorization": f"Bearer {settings.WHAPI_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Construir el payload según si hay opciones o no
        if opciones and len(opciones) > 0:
            # Mensaje con botones
            url = f"{settings.WHAPI_API_URL}/messages/interactive/buttons"
            payload = {
                "to": numero_destino,
                "body": mensaje,  # Aquí está el parámetro 'body' para botones
                "buttons": [{"id": f"btn_{i}", "text": opcion} for i, opcion in enumerate(opciones)]
            }
        else:
            # Mensaje de texto simple
            url = f"{settings.WHAPI_API_URL}/messages/text"
            # Para mensajes de texto simples, también usar 'body' en lugar de 'message'
            payload = {
                "to": numero_destino,
                "body": mensaje  # Cambiado de 'message' a 'body' para consistencia
            }
        
        # Debug: mostrar URL y payload
        logger.debug(f"URL: {url}")
        logger.debug(f"Payload: {json.dumps(payload)}")
        
        # Enviar el mensaje
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=15.0)
            
            # Log detallado de la respuesta
            logger.debug(f"Status: {response.status_code}")
            logger.debug(f"Response: {response.text}")
            
            if response.status_code != 200:
                logger.error(f"Error enviando mensaje: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
            
            response_data = response.json()
            logger.info(f"Mensaje enviado correctamente: {response_data.get('id', 'unknown')}")
            
            return {
                "success": True, 
                "message_id": response_data.get("id"),
                "response": response_data
            }
            
    except Exception as e:
        logger.exception(f"Error enviando mensaje WhatsApp: {str(e)}")
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