import httpx
import logging
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

async def enviar_mensaje_whatsapp(numero: str, mensaje: str):
    """
    Envía un mensaje usando gate.whapi.cloud
    """
    # Asegurarse que el número tenga el formato correcto
    if not numero.endswith("@c.us"):
        numero = f"{numero}@c.us"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.WHAPI_API_URL}/messages/text",
                headers={
                    "Authorization": settings.WHAPI_TOKEN,
                    "Content-Type": "application/json"
                },
                json={
                    "chatId": numero,
                    "text": mensaje
                }
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"Error enviando mensaje WhatsApp: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error enviando mensaje de WhatsApp: {str(e)}"
            )