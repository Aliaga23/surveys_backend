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
    tipo_mensaje: str = "normal"  # Puede ser "normal", "confirmacion", "opciones"
) -> Dict:
    """
    Envía un mensaje por WhatsApp usando la API de Whapi.
    
    Args:
        numero_destino: Número de teléfono del destinatario
        mensaje: Texto del mensaje
        opciones: Lista de opciones para mostrar (opcional)
        tipo_mensaje: Tipo de mensaje a enviar ("normal", "confirmacion", "opciones")
    
    Returns:
        Dict con información sobre el resultado del envío
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
        
        # Determinar URL base
        api_url = settings.WHAPI_API_URL or "https://gate.whapi.cloud"
        
        # Construir el payload según el tipo de mensaje
        if tipo_mensaje == "confirmacion":
            # Mensaje de confirmación Sí/No para iniciar encuesta
            url = f"{api_url}/messages/interactive"
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
                    "text": "Por favor responde para continuar"
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
        elif tipo_mensaje == "opciones" and opciones and len(opciones) > 0:
            # Mensaje con opciones múltiples para preguntas tipo 3
            url = f"{api_url}/messages/interactive"
            
            # Preparar botones para todas las opciones
            botones = []
            for i, opcion in enumerate(opciones):
                # Limitar la longitud del título a 20 caracteres (límite de WhatsApp)
                titulo = opcion[:20] if len(opcion) > 20 else opcion
                botones.append({
                    "type": "quick_reply",
                    "title": titulo,
                    "id": f"btn_{i}"
                })
                
            payload = {
                "to": numero_destino,
                "type": "button",
                "header": {
                    "text": "Selección"
                },
                "body": {
                    "text": mensaje
                },
                "footer": {
                    "text": "Selecciona una opción"
                },
                "action": {
                    "buttons": botones[:3]  # Máximo 3 botones permitidos
                }
            }
            
            # Si hay más de 3 opciones, necesitamos manejarlas diferentemente
            if len(opciones) > 3:
                # Cambiamos a tipo lista que permite más opciones
                payload = {
                    "to": numero_destino,
                    "type": "list",
                    "header": {
                        "text": "Selección"
                    },
                    "body": {
                        "text": mensaje
                    },
                    "footer": {
                        "text": "Haz clic para ver las opciones"
                    },
                    "action": {
                        "list": {
                            "sections": [
                                {
                                    "title": "Opciones disponibles",
                                    "rows": [
                                        {
                                            "id": f"opt_{i}",
                                            "title": opcion[:24]  # Limitar longitud
                                        } for i, opcion in enumerate(opciones)
                                    ]
                                }
                            ],
                            "label": "Ver opciones"
                        }
                    }
                }
        else:
            # Mensaje de texto simple
            url = f"{api_url}/messages/text"
            payload = {
                "to": numero_destino,
                "body": mensaje
            }
            
            # Si hay opciones pero no es tipo "opciones", añadir al texto
            if opciones and len(opciones) > 0:
                opciones_texto = "\n".join([f"• {i+1}. {opcion}" for i, opcion in enumerate(opciones)])
                payload["body"] += f"\n\nOpciones disponibles:\n{opciones_texto}"
        
        # Debug: mostrar URL y payload
        logger.debug(f"URL: {url}")
        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
        
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