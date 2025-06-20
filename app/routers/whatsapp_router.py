from fastapi import APIRouter, Depends, status, Request, Response
from sqlalchemy.orm import Session
import logging
import re
import json
from typing import Dict
from sqlalchemy import or_

from app.core.database import get_db
from app.core.config import settings
from app.models.survey import ConversacionEncuesta
from app.services.conversacion_service import procesar_respuesta
from app.services.entregas_service import get_entrega_by_destinatario, iniciar_conversacion_whatsapp
from app.services.whatsapp_service import enviar_mensaje_whatsapp
from app.models.survey import EntregaEncuesta, ConversacionEncuesta, Destinatario
from app.models.survey import RespuestaTemp
from app.core.constants import ESTADO_RESPONDIDO

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# Estado de la conversación por usuario
conversaciones_estado: Dict[str, str] = {}

@router.post("/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Webhook para recibir mensajes de Whapi
    """
    try:
        # Obtener el cuerpo del mensaje
        body = await request.json()
        
        # Extraer datos del mensaje
        chat_id = body.get("waId")
        texto = body.get("text", "").strip()
        
        print(f"Mensaje recibido de {chat_id}: {texto}")
        
        # Verificar datos básicos
        if not chat_id or not texto:
            return {"success": False, "message": "Datos incompletos"}
        
        # Normalizar número de teléfono (quitar @c.us si existe)
        if '@' in chat_id:
            chat_id = chat_id.split('@')[0]
        
        # Obtener el estado actual de la conversación
        estado_actual = conversaciones_estado.get(chat_id, 'sin_estado')
        print(f"Estado actual para {chat_id}: {estado_actual}")
        
        # Buscar si hay una entrega pendiente para este número
        entrega = None
        conversacion = None
        
        if estado_actual == 'esperando_confirmacion':
            # Buscar la entrega asociada al número
            entrega = (
                db.query(EntregaEncuesta)
                .join(Destinatario)
                .filter(
                    or_(
                        Destinatario.telefono == chat_id,
                        Destinatario.telefono == f"{chat_id}@c.us"
                    )
                )
                .order_by(EntregaEncuesta.enviado_en.desc())
                .first()
            )
            
            respuesta_normalizada = texto.strip().lower()
            
            # Si confirma iniciar la encuesta
            if re.match(r'(s[iíì]|yes|ok|okay|vale|claro|por supuesto|adelante|iniciar)', respuesta_normalizada):
                print("Usuario confirmó iniciar la encuesta")
                # Iniciar la conversación de la encuesta
                await iniciar_conversacion_whatsapp(db, entrega.id)
                
                # Actualizar el estado
                conversaciones_estado[chat_id] = 'encuesta_en_progreso'
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
                return {"success": True, "message": "Clarification requested"}
            
        elif estado_actual == 'encuesta_en_progreso':
            print("Procesando respuesta para encuesta en progreso")
            
            # Buscar la entrega asociada al número
            entrega = (
                db.query(EntregaEncuesta)
                .join(Destinatario)
                .filter(
                    or_(
                        Destinatario.telefono == chat_id,
                        Destinatario.telefono == f"{chat_id}@c.us"
                    )
                )
                .order_by(EntregaEncuesta.enviado_en.desc())
                .first()
            )
            
            if not entrega:
                print("Entrega no encontrada")
                await enviar_mensaje_whatsapp(chat_id, "Lo sentimos, no encontramos tu encuesta activa. Por favor, escribe 'INICIAR' para comenzar.")
                conversaciones_estado[chat_id] = 'sin_estado'
                return {"success": False, "message": "Entrega no encontrada"}
            
            # Buscar la conversación activa
            conversacion = (
                db.query(ConversacionEncuesta)
                .filter(ConversacionEncuesta.entrega_id == entrega.id)
                .first()
            )
            
            if not conversacion:
                print("Conversación no encontrada")
                await enviar_mensaje_whatsapp(chat_id, "Lo sentimos, no encontramos tu conversación activa. Por favor, escribe 'INICIAR' para comenzar.")
                conversaciones_estado[chat_id] = 'sin_estado'
                return {"success": False, "message": "Conversación no encontrada"}
                
            # Verificar si la conversación ya está completada
            if conversacion.completada:
                mensaje = "Esta encuesta ya ha sido completada. Gracias por tu participación."
                await enviar_mensaje_whatsapp(chat_id, mensaje)
                # Eliminar el estado de la conversación
                conversaciones_estado.pop(chat_id, None)
                return {"success": True, "message": "Survey already completed"}
                
            # Procesar la respuesta
            resultado = await procesar_respuesta(db, conversacion.id, texto)
            
            # Si hay error, enviar mensaje de error y mantener el estado actual
            if "error" in resultado:
                print(f"Error en respuesta: {resultado['error']}")
                await enviar_mensaje_whatsapp(chat_id, resultado["error"])
                return {"success": True, "message": "Error handled"}
            
            # Si la encuesta está completada, enviar mensaje final y limpiar el estado
            if resultado.get("completada", False):
                print("Encuesta completada")
                mensaje_final = "¡Muchas gracias por completar la encuesta! Tus respuestas han sido registradas correctamente."
                
                if resultado.get("respuesta_id"):
                    mensaje_final += f"\n\nCódigo de referencia: {resultado['respuesta_id'][:8]}"
                
                await enviar_mensaje_whatsapp(chat_id, mensaje_final)
                
                # Eliminar el estado de la conversación
                conversaciones_estado.pop(chat_id, None)
                
                return {"success": True, "message": "Survey completed", "respuesta_id": resultado.get("respuesta_id")}
            
            # Si hay siguiente pregunta, enviarla con las opciones si es necesario
            print(f"Enviando siguiente pregunta: {resultado['siguiente_pregunta'][:30]}...")
            
            if resultado.get("opciones"):
                await enviar_mensaje_whatsapp(chat_id, resultado["siguiente_pregunta"], resultado["opciones"])
            else:
                await enviar_mensaje_whatsapp(chat_id, resultado["siguiente_pregunta"])
            
            return {"success": True, "message": "Next question sent"}
        
        # Si no hay estado o el mensaje es INICIAR, buscar entrega pendiente
        elif texto.upper() == "INICIAR":
            print("Usuario quiere iniciar una encuesta")
            
            # Buscar si hay una entrega pendiente para este número
            entrega = (
                db.query(EntregaEncuesta)
                .join(Destinatario)
                .filter(
                    or_(
                        Destinatario.telefono == chat_id,
                        Destinatario.telefono == f"{chat_id}@c.us"
                    ),
                    EntregaEncuesta.canal_id == 2,  # Canal WhatsApp
                    EntregaEncuesta.estado_id != ESTADO_RESPONDIDO  # No respondida
                )
                .order_by(EntregaEncuesta.enviado_en.desc())
                .first()
            )
            
            if entrega:
                # Enviar mensaje de confirmación
                nombre = entrega.destinatario.nombre or "Hola"
                mensaje = f"{nombre}, estamos a punto de iniciar la encuesta '{entrega.campana.nombre}'. ¿Deseas comenzar ahora? Responde SÍ para iniciar."
                await enviar_mensaje_whatsapp(chat_id, mensaje)
                
                # Actualizar estado
                conversaciones_estado[chat_id] = 'esperando_confirmacion'
                return {"success": True, "message": "Confirmation requested"}
            else:
                # No hay entregas pendientes
                mensaje = "No encontramos encuestas pendientes para tu número. Si crees que es un error, por favor contacta con el administrador."
                await enviar_mensaje_whatsapp(chat_id, mensaje)
                return {"success": True, "message": "No pending surveys"}
        
        # Estado desconocido, reiniciar
        else:
            print(f"Estado desconocido: {estado_actual}, reiniciando")
            await enviar_mensaje_whatsapp(
                chat_id,
                "Hola. Para iniciar o continuar con la encuesta, por favor escribe 'INICIAR'."
            )
            conversaciones_estado[chat_id] = 'sin_estado'
            return {"success": True, "message": "Reset state"}
            
    except Exception as e:
        print(f"Error en webhook: {str(e)}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

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