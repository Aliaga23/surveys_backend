from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
import logging
import re

from app.core.database import get_db
from app.services.conversacion_service import procesar_respuesta
from app.services.entregas_service import get_entrega_by_destinatario, iniciar_conversacion_whatsapp
from app.services.whatsapp_service import enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# Estado de la conversación por usuario
# {numero_telefono: estado}
# Posibles estados: 'esperando_confirmacion', 'encuesta_en_progreso'
conversaciones_estado = {}

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
        print("Payload recibido:", payload)
        chat_id = payload.get("chatId", "")  # Formato: 1234567890@c.us
        if not chat_id or "@c.us" not in chat_id:
            return {"success": False, "error": "Invalid chatId"}
        
        numero = chat_id.split("@")[0]
        texto = payload.get("text", {}).get("message", "")
        
        logger.info(f"Mensaje recibido de {numero}: {texto}")
        
        # Obtener estado actual de la conversación
        estado_actual = conversaciones_estado.get(numero, 'esperando_confirmacion')
        
        # Buscar entrega por número de teléfono
        entrega = get_entrega_by_destinatario(db, telefono=numero)
        if not entrega:
            await enviar_mensaje_whatsapp(
                chat_id,
                "Hola 👋 Lo siento, no encontré ninguna encuesta pendiente para este número."
            )
            return {"success": True}
        
        # Si está esperando confirmación para iniciar la encuesta
        if estado_actual == 'esperando_confirmacion':
            respuesta_normalizada = texto.strip().lower()
            
            # Si confirma iniciar la encuesta
            if re.match(r'(s[iíì]|yes|ok|okay|vale|claro|por supuesto|adelante)', respuesta_normalizada):
                try:
                    # Iniciar la conversación de la encuesta
                    await iniciar_conversacion_whatsapp(db, entrega.id)
                    
                    # Actualizar el estado
                    conversaciones_estado[numero] = 'encuesta_en_progreso'
                    return {"success": True}
                except Exception as e:
                    logger.error(f"Error iniciando encuesta: {str(e)}")
                    await enviar_mensaje_whatsapp(
                        chat_id,
                        "Lo siento, ocurrió un error al iniciar la encuesta. Por favor intenta nuevamente en unos minutos."
                    )
                    return {"success": False, "error": str(e)}
            
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
            if not entrega.conversacion:
                # Si por alguna razón no existe la conversación, reiniciar
                await iniciar_conversacion_whatsapp(db, entrega.id)
                return {"success": True}
            
            # Procesar la respuesta normalmente
            resultado = await procesar_respuesta(db, entrega.conversacion.id, texto)
            
            if "error" in resultado:
                await enviar_mensaje_whatsapp(chat_id, resultado["error"])
            else:
                await enviar_mensaje_whatsapp(
                    chat_id, 
                    resultado["siguiente_pregunta"],
                    resultado.get("opciones")
                )
                
                # Si se completó la encuesta
                if resultado.get("completada", False):
                    await enviar_mensaje_whatsapp(
                        chat_id,
                        "¡Muchas gracias por completar la encuesta! Tus respuestas son muy valiosas para nosotros."
                    )
                    # Restablecer estado
                    if numero in conversaciones_estado:
                        del conversaciones_estado[numero]
            
            return {"success": True}
        
        # Estado desconocido
        else:
            # Mensaje genérico para reanudar
            await enviar_mensaje_whatsapp(
                chat_id,
                "Hola de nuevo. Para iniciar o continuar con la encuesta, por favor escribe 'INICIAR'."
            )
            conversaciones_estado[numero] = 'esperando_confirmacion'
            return {"success": True}
        
    except Exception as e:
        logger.error(f"Error procesando webhook: {str(e)}")
        # Intentar enviar mensaje de error si es posible
        try:
            if 'chat_id' in locals():
                await enviar_mensaje_whatsapp(
                    chat_id,
                    "Lo siento, ha ocurrido un error al procesar tu mensaje. Por favor, intenta nuevamente más tarde."
                )
        except:
            pass
        return {"success": False, "error": str(e)}

# Endpoint adicional para reiniciar conversaciones
@router.post("/reset/{numero}")
async def reset_conversation(numero: str):
    """Reinicia el estado de conversación de un número específico"""
    if numero in conversaciones_estado:
        conversaciones_estado.pop(numero)
        return {"success": True, "message": f"Estado de conversación para {numero} reiniciado"}
    return {"success": False, "message": f"No se encontró estado para {numero}"}