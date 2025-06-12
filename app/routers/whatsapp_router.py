from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
import logging

from app.core.database import get_db
from app.services.conversacion_service import procesar_respuesta
from app.services.entregas_service import get_entrega_by_destinatario
from app.services.whatsapp_service import enviar_mensaje_whatsapp
from app.services.respuestas_service import crear_respuesta_encuesta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

@router.post("/webhook")
async def whatsapp_webhook(
    payload: dict,
    db: Session = Depends(get_db)
):
    """
    Webhook para recibir mensajes de gate.whapi.cloud
    """
    try:
        # Validar que sea un mensaje de texto
        if payload.get("messageType") != "text":
            return {"success": True}
        
        chat_id = payload.get("chatId", "")  # Formato: 1234567890@c.us
        if not chat_id or "@c.us" not in chat_id:
            return {"success": False, "error": "Invalid chatId"}
        
        numero = chat_id.split("@")[0]
        texto = payload.get("text", {}).get("message", "")
        
        # Buscar entrega por número de teléfono
        entrega = get_entrega_by_destinatario(db, telefono=numero)
        if not entrega:
            await enviar_mensaje_whatsapp(
                chat_id,
                "Lo siento, no encontré ninguna encuesta pendiente para este número."
            )
            return {"success": True}
        
        # Procesar respuesta
        resultado = await procesar_respuesta(db, entrega.conversacion.id, texto)
        
        if "error" in resultado:
            await enviar_mensaje_whatsapp(chat_id, resultado["error"])
        else:
            await enviar_mensaje_whatsapp(chat_id, resultado["siguiente_pregunta"])
            
            if resultado["completada"]:
                await crear_respuesta_encuesta(db, entrega.id, entrega.conversacion.historial)
                await enviar_mensaje_whatsapp(
                    chat_id,
                    "¡Gracias por completar la encuesta! Tus respuestas han sido registradas."
                )
        
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Error procesando webhook: {str(e)}")
        return {"success": False, "error": str(e)}