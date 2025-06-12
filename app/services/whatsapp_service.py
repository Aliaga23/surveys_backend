import httpx
import logging
from typing import List, Optional
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

async def enviar_mensaje_whatsapp(
    chat_id: str, 
    mensaje: str, 
    opciones: Optional[List[str]] = None
):
    """
    Envía un mensaje usando Whapi API con opciones si existen
    """
    # Asegurar formato correcto del chat_id (añadir @c.us si no está)
    if "@c.us" not in chat_id:
        chat_id = f"{chat_id}@c.us"
    
    # Formatear el mensaje con las opciones si existen
    mensaje_completo = mensaje
    if opciones and len(opciones) > 0:
        mensaje_completo += "\n\nOpciones disponibles:\n" + "\n".join(f"• {opcion}" for opcion in opciones)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.WHAPI_API_URL}/messages/text",
                headers={
                    "Authorization": f"Bearer {settings.WHAPI_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "chatId": chat_id,  # Usar chatId según la documentación de Whapi
                    "body": mensaje_completo  # Usar body según la documentación de Whapi
                },
                timeout=10.0
            )
            
            # Log para depuración
            logger.debug(f"Respuesta de Whapi: Status {response.status_code}")
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            error_msg = f"Error enviando mensaje WhatsApp: {str(e)}"
            logger.error(error_msg)
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response content: {e.response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )