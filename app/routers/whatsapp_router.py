from fastapi import APIRouter, Depends, status, Request, Response
from sqlalchemy.orm import Session
import logging
import re
import json
from typing import Dict

from app.core.database import get_db
from app.core.config import settings
from app.models.survey import ConversacionEncuesta
from app.services.conversacion_service import procesar_respuesta
from app.services.entregas_service import get_entrega_by_destinatario, iniciar_conversacion_whatsapp
from app.services.whatsapp_service import enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# Estado de la conversación por usuario
conversaciones_estado: Dict[str, str] = {}

@router.post("/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Webhook para recibir mensajes de Whapi
    """
    print("Webhook recibido en /whatsapp/webhook")
    
    # Verificar la firma de Whapi (opcional pero recomendado para producción)
    body = await request.body()
    payload = json.loads(body)
    
    # Log del payload completo recibido
    logger.info(f"Webhook recibido: {json.dumps(payload, indent=2)}")
    
    # Si es un mensaje de verificación de webhook
    if payload.get("event") == "webhook.verified":
        logger.info("Webhook verificado correctamente")
        return {"success": True}
        
    # Si no es un mensaje de texto, ignorar
    if payload.get("event") != "message.received" or payload.get("messageType") != "text":
        return {"success": True}
        
    # Extraer la información importante
    chat_id = payload.get("chatId", "")
    if not chat_id or "@c.us" not in chat_id:
        return {"success": False, "error": "Invalid chatId"}
    
    # Usar solo el número sin el sufijo @c.us para las búsquedas
    numero = chat_id.split("@")[0]
    
    # Extraer el texto del mensaje según la estructura correcta de Whapi
    mensaje = payload.get("text", {}).get("body", "")
    if not mensaje:
        return {"success": True}  # Ignorar mensajes vacíos
    
    logger.info(f"Mensaje recibido de {numero}: {mensaje}")
    
    # Obtener estado actual de la conversación (default: esperando_confirmacion)
    estado_actual = conversaciones_estado.get(chat_id, 'esperando_confirmacion')
    
    # Buscar entrega activa para este número
    entrega = get_entrega_by_destinatario(db, telefono=numero)
    if not entrega:
        await enviar_mensaje_whatsapp(
            chat_id,
            "Hola 👋 Lo siento, no encontré ninguna encuesta pendiente para este número."
        )
        return {"success": True}
    
    # Manejar el flujo según el estado de la conversación
    if estado_actual == 'esperando_confirmacion':
        respuesta_normalizada = mensaje.strip().lower()
        
        # Si confirma iniciar la encuesta
        if re.match(r'(s[iíì]|yes|ok|okay|vale|claro|por supuesto|adelante|iniciar)', respuesta_normalizada):
            # Iniciar la conversación de la encuesta
            await iniciar_conversacion_whatsapp(db, entrega.id)
            
            # Actualizar el estado
            conversaciones_estado[chat_id] = 'encuesta_en_progreso'
            logger.info(f"Encuesta iniciada para {chat_id}")
            return {"success": True}
        
        # Si no quiere iniciar ahora
        elif re.match(r'(no|nop|después|luego|más tarde)', respuesta_normalizada):
            mensaje_despedida = "Entendido. Puedes responder en cualquier momento escribiendo 'INICIAR'. ¡Que tengas un buen día!"
            await enviar_mensaje_whatsapp(chat_id, mensaje_despedida)
            return {"success": True}
        
        # Si la respuesta no es clara
        else:
            mensaje_aclaracion = "Por favor, responde 'SI' para comenzar la encuesta ahora o 'NO' para hacerlo más tarde."
            await enviar_mensaje_whatsapp(chat_id, mensaje_aclaracion)
            return {"success": True}
    
    # Si la encuesta ya está en progreso, procesar la respuesta
    elif estado_actual == 'encuesta_en_progreso':
        # Buscar la conversación de manera explícita
        conversacion = (
            db.query(ConversacionEncuesta)
            .filter(ConversacionEncuesta.entrega_id == entrega.id)
            .first()
        )
        
        if not conversacion:
            logger.warning(f"No hay conversación para la entrega {entrega.id}, iniciando una nueva")
            await iniciar_conversacion_whatsapp(db, entrega.id)
            return {"success": True}
        
        # Ahora podemos procesar la respuesta
        resultado = await procesar_respuesta(db, conversacion.id, mensaje)
        
        if "error" in resultado:
            await enviar_mensaje_whatsapp(chat_id, resultado["error"])
        else:
            # Enviar siguiente pregunta con opciones si existen
            await enviar_mensaje_whatsapp(
                chat_id, 
                resultado["siguiente_pregunta"],
                resultado.get("opciones")
            )
            
            # Si se completó la encuesta
            if resultado.get("completada", False):
                await enviar_mensaje_whatsapp(
                    chat_id,
                    "¡Muchas gracias por completar la encuesta! Tus respuestas son muy valiosas para nosotros. 😊"
                )
                # Restablecer estado
                conversaciones_estado.pop(chat_id, None)
                logger.info(f"Encuesta completada para {chat_id}")
        
        return {"success": True}
    
    # Estado desconocido, reiniciar
    else:
        await enviar_mensaje_whatsapp(
            chat_id,
            "Hola de nuevo. Para iniciar o continuar con la encuesta, por favor escribe 'INICIAR'."
        )
        conversaciones_estado[chat_id] = 'esperando_confirmacion'
        return {"success": True}

# Ruta de verificación (como muestra el ejemplo de Whapi-Cloud)
@router.get("/webhook")
async def verify_webhook(request: Request):
    """
    Verifica el webhook para Whapi
    """
    hub_mode = request.query_params.get('hub_mode')
    hub_challenge = request.query_params.get('hub_challenge')
    hub_verify_token = request.query_params.get('hub_verify_token')
    
    # Verificar token
    verify_token = settings.WHAPI_VERIFY_TOKEN
    
    if hub_mode == 'subscribe' and hub_verify_token == verify_token:
        logger.info("Webhook verificado correctamente")
        return Response(content=hub_challenge)
    else:
        logger.warning("Falló la verificación del webhook")
        return Response(status_code=403)

# Endpoint para reiniciar manualmente una conversación
@router.post("/reset/{numero}")
async def reset_conversation(numero: str):
    """Reinicia el estado de conversación de un número específico"""
    chat_id = f"{numero}@c.us" if "@c.us" not in numero else numero
    
    if chat_id in conversaciones_estado:
        conversaciones_estado.pop(chat_id)
        return {"success": True, "message": f"Estado de conversación para {numero} reiniciado"}
    
    return {"success": False, "message": f"No se encontró estado para {numero}"}

# Endpoint para ver el estado de todas las conversaciones
@router.get("/status")
async def get_conversation_status():
    """Obtiene el estado actual de todas las conversaciones"""
    return {"conversaciones": conversaciones_estado}