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
    Envía un mensaje usando gate.whapi.cloud con opciones si existen
    """
   
    # Formatear el mensaje con las opciones si existen
    mensaje_completo = mensaje
    if opciones and len(opciones) > 0:
        mensaje_completo += "\n\nOpciones disponibles:\n" + "\n".join(f"• {opcion}" for opcion in opciones)
    
    print(f"Enviando mensaje a {chat_id}: {mensaje_completo[:30]}...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.WHAPI_API_URL}/messages/text",
                headers={
                    "Authorization": f"Bearer {settings.WHAPI_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "to": chat_id,  # Según documentación de Whapi
                    "body": mensaje_completo  # Según documentación de Whapi
                },
                timeout=10.0
            )
            
            # Log para depuración
            print(f"Respuesta de Whapi - Status: {response.status_code}")
            if response.status_code != 200:
                print(f"Error en respuesta: {response.text}")
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error enviando mensaje: {str(e)}")
            raise e