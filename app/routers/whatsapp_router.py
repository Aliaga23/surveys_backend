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
    # Este es el primer paso para depuración
    print("Webhook recibido en /whatsapp/webhook")
    
    # Leer el cuerpo de la solicitud
    body = await request.body()
    body_str = body.decode('utf-8')
    
    # Imprimir el cuerpo completo sin procesar
    print(f"Cuerpo del webhook: {body_str}")
    
    try:
        payload = json.loads(body_str)
        # Imprimir para depuración
        print(f"Payload JSON: {payload}")
        logger.info(f"Webhook recibido: {json.dumps(payload, indent=2)}")
    except json.JSONDecodeError as e:
        print(f"Error decodificando JSON: {e}")
        return {"success": False, "error": "Invalid JSON"}
    
    # Verificar primero si es una verificación de webhook
    if payload.get("hubVerificationToken"):
        if payload["hubVerificationToken"] == settings.WHAPI_TOKEN:
            logger.info("Webhook verificado correctamente")
            return {"success": True, "message": "Webhook verified"}
        return {"success": False, "error": "Invalid verification token"}
    
    # Según la documentación, verificar si es un mensaje entrante
    if not payload.get("messages") or not isinstance(payload["messages"], list) or len(payload["messages"]) == 0:
        print("No hay mensajes en el payload")
        return {"success": True, "message": "No messages"}
    
    # Obtener el primer mensaje (pueden venir varios en batch)
    message = payload["messages"][0]
    
    # Verificar si es un mensaje de texto
    if message.get("type") != "text":
        print(f"Tipo de mensaje no es texto: {message.get('type')}")
        return {"success": True, "message": "Not a text message"}
    
    # Extraer la información importante según la estructura de Whapi
    chat_id = message.get("from", "")  # Formato: 1234567890@c.us

    # Usar solo el número sin el sufijo @c.us para las búsquedas
    numero = chat_id.split("@")[0]
    
    # Extraer el texto del mensaje según la estructura de Whapi
    texto = message.get("text", {}).get("body", "")
    if not texto:
        print("Mensaje vacío")
        return {"success": True, "message": "Empty message"}
    
    print(f"Mensaje procesado - De: {numero}, Texto: {texto}")
    logger.info(f"Mensaje recibido de {numero}: {texto}")
    
    # A partir de aquí sigue el procesamiento de la conversación
    # Obtener estado actual de la conversación
    estado_actual = conversaciones_estado.get(chat_id, 'esperando_confirmacion')
    print(f"Estado actual: {estado_actual}")
    
    # Buscar entrega activa para este número
    entrega = get_entrega_by_destinatario(db, telefono=numero)
    if not entrega:
        print(f"No se encontró entrega para el número: {numero}")
        await enviar_mensaje_whatsapp(
            chat_id,
            "Hola 👋 Lo siento, no encontré ninguna encuesta pendiente para este número."
        )
        return {"success": True, "message": "No entrega found"}
    
    print(f"Entrega encontrada ID: {entrega.id}")
    
    # Manejar el flujo según el estado de la conversación
    if estado_actual == 'esperando_confirmacion':
        respuesta_normalizada = texto.strip().lower()
        
        # Si confirma iniciar la encuesta
        if re.match(r'(s[iíì]|yes|ok|okay|vale|claro|por supuesto|adelante|iniciar)', respuesta_normalizada):
            print("Usuario confirmó iniciar la encuesta")
            # Iniciar la conversación de la encuesta
            await iniciar_conversacion_whatsapp(db, entrega.id)
            
            # Actualizar el estado
            conversaciones_estado[chat_id] = 'encuesta_en_progreso'
            print(f"Estado actualizado: {conversaciones_estado[chat_id]}")
            return {"success": True, "message": "Survey started"}
        
        # Si no quiere iniciar ahora
        elif re.match(r'(no|nop|después|luego|más tarde)', respuesta_normalizada):
            print("Usuario declinó iniciar la encuesta")
            mensaje_despedida = "Entendido. Puedes responder en cualquier momento escribiendo 'INICIAR'. ¡Que tengas un buen día!"
            await enviar_mensaje_whatsapp(chat_id, mensaje_despedida)
            return {"success": True, "message": "Survey declined"}
        
        # Si la respuesta no es clara
        else:
            print("Respuesta no clara, pidiendo confirmación")
            mensaje_aclaracion = "Por favor, responde 'SI' para comenzar la encuesta ahora o 'NO' para hacerlo más tarde."
            await enviar_mensaje_whatsapp(chat_id, mensaje_aclaracion)
            return {"success": True, "message": "Confirmation requested"}
    
    # Si la encuesta ya está en progreso, procesar la respuesta
    elif estado_actual == 'encuesta_en_progreso':
        print("Procesando respuesta para encuesta en progreso")
        # Buscar la conversación de manera explícita
        conversacion = (
            db.query(ConversacionEncuesta)
            .filter(ConversacionEncuesta.entrega_id == entrega.id)
            .first()
        )
        
        if not conversacion:
            print(f"No hay conversación para la entrega {entrega.id}, iniciando una nueva")
            await iniciar_conversacion_whatsapp(db, entrega.id)
            return {"success": True, "message": "New conversation started"}
        
        print(f"Conversación encontrada ID: {conversacion.id}")
        
        # Ahora podemos procesar la respuesta
        resultado = await procesar_respuesta(db, conversacion.id, texto)
        
        if "error" in resultado:
            print(f"Error en respuesta: {resultado['error']}")
            await enviar_mensaje_whatsapp(chat_id, resultado["error"])
            return {"success": True, "message": "Error handled"}
        else:
            # Enviar siguiente pregunta con opciones si existen
            print(f"Enviando siguiente pregunta: {resultado['siguiente_pregunta'][:30]}...")
            await enviar_mensaje_whatsapp(
                chat_id, 
                resultado["siguiente_pregunta"],
                resultado.get("opciones")
            )
            
            # Si se completó la encuesta
            if resultado.get("completada", False):
                print("Encuesta completada")
                await enviar_mensaje_whatsapp(
                    chat_id,
                    "¡Muchas gracias por completar la encuesta! Tus respuestas son muy valiosas para nosotros. 😊"
                )
                # Restablecer estado
                conversaciones_estado.pop(chat_id, None)
                print(f"Estado de conversación reiniciado para {chat_id}")
                return {"success": True, "message": "Survey completed"}
            return {"success": True, "message": "Next question sent"}
    
    # Estado desconocido, reiniciar
    else:
        print(f"Estado desconocido: {estado_actual}, reiniciando")
        await enviar_mensaje_whatsapp(
            chat_id,
            "Hola de nuevo. Para iniciar o continuar con la encuesta, por favor escribe 'INICIAR'."
        )
        conversaciones_estado[chat_id] = 'esperando_confirmacion'
        return {"success": True, "message": "State reset"}

@router.get("/webhook")
async def verify_webhook(request: Request):
    """
    Verifica el webhook para Whapi según la documentación oficial
    """
    mode = request.query_params.get('hub.mode')
    challenge = request.query_params.get('hub.challenge')
    token = request.query_params.get('hub.verify_token')
    
    print(f"Verificación de webhook - Mode: {mode}, Challenge: {challenge}, Token: {token}")
    
    # Verificar token
    verify_token = settings.WHAPI_VERIFY_TOKEN
    
    if mode == 'subscribe' and token == verify_token:
        print("Webhook verificado correctamente")
        logger.info("Webhook verificado correctamente")
        return Response(content=challenge)
    else:
        print("Falló la verificación del webhook")
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