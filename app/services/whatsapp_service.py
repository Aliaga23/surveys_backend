import httpx
import logging
from typing import List, Optional
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

async def enviar_mensaje_whatsapp(
    numero: str, 
    mensaje: str, 
    opciones: Optional[List[str]] = None
):
    """
    Envía un mensaje usando gate.whapi.cloud con opciones si existen
    """
    numero = numero.split('@')[0] if '@' in numero else numero
    
    # Formatear el mensaje con las opciones si existen
    mensaje_completo = mensaje
    if opciones:
        mensaje_completo += "\n\nOpciones disponibles:\n" + "\n".join(f"• {opcion}" for opcion in opciones)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.WHAPI_API_URL}/messages/text",
                headers={
                    "Authorization": settings.WHAPI_TOKEN,
                    "Content-Type": "application/json"
                },
                json={
                    "to": numero,
                    "body": mensaje_completo
                },
                timeout=10.0
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            error_msg = f"Error enviando mensaje WhatsApp: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Response content: {e.response.text if hasattr(e, 'response') else 'No response'}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )