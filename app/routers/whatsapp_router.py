from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy.orm import Session
import logging
import json
import re
import traceback
from typing import Dict, Any, List
from uuid import UUID

from app.core.database import get_db
from app.core.config import settings
from app.models.survey import CampanaEncuesta, ConversacionEncuesta, EntregaEncuesta, PlantillaEncuesta, PreguntaEncuesta
from app.services.conversacion_service import procesar_respuesta
from app.services.entregas_service import get_entrega_by_destinatario, iniciar_conversacion_whatsapp
from app.services.whatsapp_service import enviar_mensaje_whatsapp, procesar_webhook_whatsapp

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# Estado de la conversación por usuario - almacena el estado actual de cada conversación
# llave: número de teléfono, valor: estado ('esperando_confirmacion', 'encuesta_en_progreso', etc.)
conversaciones_estado: Dict[str, str] = {}

@router.post("/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Webhook para recibir mensajes y eventos de Whapi.
    
    Este endpoint procesa los mensajes entrantes por WhatsApp y maneja el flujo
    de conversación para las encuestas.
    """
    try:
        # Leer y decodificar el cuerpo de la solicitud
        body = await request.body()
        body_str = body.decode('utf-8')
        logger.debug(f"Webhook recibido: {body_str[:200]}...")
        
        # Parsear el JSON
        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError as e:
            logger.error(f"Error decodificando JSON: {str(e)}")
            return {"success": False, "error": "Invalid JSON"}
            
        # Procesar el webhook para extraer información relevante
        resultado = await procesar_webhook_whatsapp(payload)
        
        # Verificación del webhook
        if payload.get("hubVerificationToken"):
            if payload["hubVerificationToken"] == settings.WHAPI_TOKEN:
                logger.info("Verificación de webhook exitosa")
                return {"success": True, "message": "Webhook verified"}
            return {"success": False, "error": "Invalid verification token"}
            
        # Ignorar mensajes de estado
        if resultado["tipo"] == "estado":
            return {"success": True, "message": "Status update received"}
            
        # Ignorar mensajes que no son texto
        if resultado["tipo"] == "no_texto":
            logger.info(f"Mensaje no texto recibido: {resultado['subtipo']}")
            return {"success": True, "message": f"Non-text message received: {resultado['subtipo']}"}
            
        # Ignorar mensajes enviados por nosotros mismos
        if resultado["tipo"] == "propio":
            return {"success": True, "message": "Own message ignored"}
            
        # Si no es un mensaje válido, terminar
        if resultado["tipo"] not in ["mensaje"]:
            return {"success": True, "message": f"Ignoring {resultado['tipo']}"}
        
        # Extraer información del mensaje
        numero = resultado["numero"]
        texto = resultado["texto"]
        chat_id = f"{numero}@c.us"  # Formato para enviar mensajes de vuelta
        
        logger.info(f"Mensaje recibido de {numero}: {texto[:50]}...")
        
        # Obtener el estado actual de la conversación
        estado_actual = conversaciones_estado.get(chat_id, 'esperando_confirmacion')
        logger.info(f"Estado actual para {numero}: {estado_actual}")
        
        # Buscar si existe una entrega para este número
        entrega = get_entrega_by_destinatario(db, telefono=numero)
        if not entrega:
            logger.warning(f"No se encontró entrega para el número: {numero}")
            await enviar_mensaje_whatsapp(
                chat_id,
                "Hola 👋 No encontré ninguna encuesta pendiente para este número. Por favor contacta al administrador si crees que es un error."
            )
            return {"success": True, "message": "No entrega found"}
            
        logger.info(f"Entrega encontrada ID: {entrega.id}, estado: {entrega.estado_id}")
        
        # Manejar flujo según el estado actual
        if estado_actual == 'esperando_confirmacion':
            respuesta_normalizada = texto.strip().lower()
            
            es_confirmacion = (
                respuesta_normalizada in ['si', 'sí', 'yes', 'ok', 'okay'] or
                'btn_si' in respuesta_normalizada
            )
            
            es_negacion = (
                respuesta_normalizada in ['no', 'nop', 'not'] or
                'btn_no' in respuesta_normalizada
            )
            
            if es_confirmacion:
                logger.info(f"Usuario {numero} confirmó iniciar la encuesta")
                try:
                    # Enviar primera pregunta y actualizar estado
                    await enviar_primera_pregunta(db, entrega.id, chat_id)
                    conversaciones_estado[chat_id] = 'encuesta_en_progreso'
                    return {"success": True, "message": "First question sent"}
                    
                except Exception as e:
                    logger.error(f"Error iniciando encuesta: {str(e)}")
                    await enviar_mensaje_whatsapp(
                        chat_id,
                        "Lo siento, ocurrió un error. Escribe 'INICIAR' para intentar nuevamente."
                    )
                    return {"success": False, "error": str(e)}

            # Usuario declina iniciar ahora
            elif es_negacion:
                logger.info(f"Usuario {numero} declinó iniciar la encuesta")
                
                await enviar_mensaje_whatsapp(
                    chat_id,
                    "Entendido. Puedes responder en cualquier momento escribiendo 'INICIAR'. ¡Que tengas un buen día!"
                )
                
                # No cambiamos el estado, sigue en esperando_confirmacion
                return {"success": True, "message": "Survey declined"}
                
            # Respuesta no clara, pedir confirmación explícita
            else:
                logger.info(f"Respuesta no clara de {numero}: '{texto}'")
                
                await enviar_mensaje_whatsapp(
                    chat_id,
                    "Por favor, responde 'SÍ' para comenzar la encuesta ahora o 'NO' para hacerlo más tarde."
                )
                
                return {"success": True, "message": "Clarification requested"}
                
        # Encuesta en progreso - procesamos respuesta actual y enviamos siguiente pregunta
        elif estado_actual == 'encuesta_en_progreso':
            logger.info(f"Procesando respuesta de {numero} para encuesta en progreso")
            
            # Buscar la conversación activa
            conversacion = (
                db.query(ConversacionEncuesta)
                .filter(ConversacionEncuesta.entrega_id == entrega.id)
                .first()
            )
            
            # Si no existe conversación, iniciar una nueva
            if not conversacion:
                logger.warning(f"No hay conversación para entrega {entrega.id}, iniciando una nueva")
                
                try:
                    await iniciar_conversacion_whatsapp(db, entrega.id)
                    return {"success": True, "message": "New conversation started"}
                except Exception as e:
                    logger.error(f"Error iniciando conversación: {str(e)}")
                    await enviar_mensaje_whatsapp(
                        chat_id,
                        "Lo siento, ocurrió un error. Por favor, escribe 'INICIAR' para intentar nuevamente."
                    )
                    return {"success": False, "error": str(e)}
            
            logger.info(f"Conversación encontrada ID: {conversacion.id}, completada: {conversacion.completada}")
            
            # Si la conversación ya está completada
            if conversacion.completada:
                logger.info(f"La conversación {conversacion.id} ya está completada")
                
                await enviar_mensaje_whatsapp(
                    chat_id,
                    "Esta encuesta ya ha sido completada. Gracias por tu participación."
                )
                
                # Eliminar el estado
                if chat_id in conversaciones_estado:
                    conversaciones_estado.pop(chat_id)
                    logger.info(f"Estado eliminado para {numero}")
                    
                return {"success": True, "message": "Survey already completed"}
                
            # Procesar la respuesta del usuario
            try:
                resultado = await procesar_respuesta(db, conversacion.id, texto)
                
                # Si hay error en el procesamiento de la respuesta
                if "error" in resultado:
                    logger.warning(f"Error procesando respuesta de {numero}: {resultado['error']}")
                    
                    await enviar_mensaje_whatsapp(chat_id, resultado["error"])
                    return {"success": True, "message": "Error handled"}
                    
                # Si la encuesta ha sido completada
                if resultado.get("completada", False):
                    logger.info(f"Encuesta completada para {numero}")
                    
                    # Obtener ID de respuesta si existe
                    respuesta_id = resultado.get("respuesta_id", "")
                    
                    # Mensaje personalizado de agradecimiento
                    mensaje_final = "¡Muchas gracias por completar la encuesta! Tus respuestas son muy valiosas para nosotros. 😊"
                    
                    # Añadir código de referencia
                    if respuesta_id:
                        mensaje_final += f"\n\nCódigo de referencia: {respuesta_id[:8]}"
                        
                    await enviar_mensaje_whatsapp(chat_id, mensaje_final)
                    
                    # Eliminar el estado
                    if chat_id in conversaciones_estado:
                        conversaciones_estado.pop(chat_id)
                        logger.info(f"Estado eliminado para {numero}")
                        
                    return {
                        "success": True,
                        "message": "Survey completed",
                        "respuesta_id": respuesta_id
                    }
                    
                # Si hay siguiente pregunta
                logger.info(f"Enviando siguiente pregunta a {numero}")
                
                # Enviar pregunta con opciones si existen
                if resultado.get("opciones") and resultado.get("tipo_pregunta") == 3:  # Tipo 3 = selección única
                    await enviar_mensaje_whatsapp(
                        chat_id, 
                        resultado["siguiente_pregunta"], 
                        resultado["opciones"],
                        tipo_mensaje="opciones"  # Usar formato interactivo para opciones
                    )
                else:
                    # Para otros tipos de preguntas usar formato normal
                    await enviar_mensaje_whatsapp(
                        chat_id, 
                        resultado["siguiente_pregunta"],
                        resultado.get("opciones")
                    )
                    
                return {"success": True, "message": "Next question sent"}
                
            except Exception as e:
                logger.error(f"Error procesando respuesta: {traceback.format_exc()}")
                
                await enviar_mensaje_whatsapp(
                    chat_id,
                    "Lo siento, ocurrió un error al procesar tu respuesta. Por favor, intenta nuevamente o escribe 'INICIAR' para reiniciar."
                )
                
                return {"success": False, "error": str(e)}
                
        # Si el mensaje es "INICIAR", iniciar/reiniciar el proceso
        elif texto.upper() == "INICIAR":
            logger.info(f"Usuario {numero} solicitó iniciar encuesta")
            
            # Actualizar estado
            conversaciones_estado[chat_id] = 'esperando_confirmacion'
            
            # Mensaje personalizado de bienvenida con botones Sí/No
            nombre = entrega.destinatario.nombre or "Hola"
            mensaje = f"{nombre}, estamos a punto de iniciar la encuesta '{entrega.campana.nombre}'. ¿Deseas comenzar ahora?"
            
            await enviar_mensaje_whatsapp(
                chat_id,
                mensaje,
                tipo_mensaje="confirmacion"  # Especificar tipo confirmación para botones Sí/No
            )
            return {"success": True, "message": "Confirmation requested"}
            
        # Estado desconocido o cualquier otro mensaje, reiniciar
        else:
            logger.info(f"Mensaje no reconocido de {numero}: '{texto}', estado: {estado_actual}")
            
            await enviar_mensaje_whatsapp(
                chat_id,
                "Para iniciar o continuar con la encuesta, por favor escribe 'INICIAR'."
            )
            
            conversaciones_estado[chat_id] = 'esperando_confirmacion'
            return {"success": True, "message": "State reset"}
            
    except Exception as e:
        logger.error(f"Error en webhook: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}

@router.get("/webhook")
async def verify_webhook(request: Request):
    """
    Endpoint para verificación del webhook por parte de Whapi.
    
    Whapi envía una solicitud GET a este endpoint para verificar que el webhook
    está configurado correctamente.
    """
    mode = request.query_params.get('hub.mode')
    challenge = request.query_params.get('hub.challenge')
    token = request.query_params.get('hub.verify_token')
    
    logger.info(f"Verificación de webhook - Mode: {mode}, Challenge: {challenge}")
    
    # Verificar token
    verify_token = settings.WHAPI_TOKEN
    
    if mode == 'subscribe' and token == verify_token:
        logger.info("Webhook verificado correctamente")
        return Response(content=challenge)
    else:
        logger.warning("Falló la verificación del webhook")
        return Response(status_code=403)

@router.post("/reset/{numero}")
async def reset_conversation(numero: str):
    """
    Reinicia el estado de conversación de un número específico.
    
    Útil para depuración o cuando una conversación se queda en un estado incorrecto.
    """
    # Normalizar el número
    if '@' in numero:
        chat_id = numero
    else:
        chat_id = f"{numero}@c.us"
    
    # Verificar si existe un estado para este número
    if chat_id in conversaciones_estado:
        estado_anterior = conversaciones_estado[chat_id]
        conversaciones_estado.pop(chat_id)
        return {
            "success": True, 
            "message": f"Estado de conversación para {numero} reiniciado", 
            "estado_anterior": estado_anterior
        }
    
    return {"success": False, "message": f"No se encontró estado para {numero}"}

@router.get("/status")
async def get_conversation_status():
    """
    Obtiene el estado actual de todas las conversaciones.
    
    Útil para monitoreo y depuración.
    """
    # Contar cuántas conversaciones hay en cada estado
    estados_count = {}
    for estado in conversaciones_estado.values():
        estados_count[estado] = estados_count.get(estado, 0) + 1
    
    return {
        "total_conversaciones": len(conversaciones_estado),
        "resumen_estados": estados_count,
        "conversaciones": conversaciones_estado
    }

@router.post("/send")
async def send_whatsapp_message(
    numero: str,
    mensaje: str,
    opciones: List[str] = None
):
    """
    Envía un mensaje de WhatsApp a un número específico.
    
    Útil para pruebas manuales o envío de notificaciones fuera del flujo normal.
    """
    resultado = await enviar_mensaje_whatsapp(numero, mensaje, opciones)
    return resultado

async def enviar_siguiente_pregunta(chat_id: str, pregunta_info: Dict):
    """Envía la siguiente pregunta según su tipo"""
    if pregunta_info.get("tipo_pregunta") == 3:  # Selección única
        await enviar_mensaje_whatsapp(
            chat_id,
            pregunta_info["siguiente_pregunta"],
            opciones=pregunta_info["opciones"],
            tipo_mensaje="lista"
        )
    elif pregunta_info.get("tipo_pregunta") == 4:  # Selección múltiple
        mensaje = (
            f"{pregunta_info['siguiente_pregunta']}\n\n"
            "Puedes seleccionar varias opciones separándolas por comas."
        )
        await enviar_mensaje_whatsapp(
            chat_id,
            mensaje,
            opciones=pregunta_info["opciones"],
            tipo_mensaje="lista"
        )
    elif pregunta_info.get("tipo_pregunta") == 2:  # Número
        mensaje = (
            f"{pregunta_info['siguiente_pregunta']}\n\n"
            "Por favor, responde con un número."
        )
        await enviar_mensaje_whatsapp(chat_id, mensaje)
    else:  # Texto libre
        await enviar_mensaje_whatsapp(chat_id, pregunta_info["siguiente_pregunta"])

async def enviar_primera_pregunta(db: Session, entrega_id: UUID, chat_id: str):
    """Envía la primera pregunta de la encuesta"""
    try:
        # Primero crear/obtener la conversación
        conversacion = (
            db.query(ConversacionEncuesta)
            .filter(ConversacionEncuesta.entrega_id == entrega_id)
            .first()
        )

        if not conversacion:
            # Si no existe, crear nueva conversación
            conversacion = await iniciar_conversacion_whatsapp(db, entrega_id)

        # Obtener la pregunta actual
        pregunta = (
            db.query(PreguntaEncuesta)
            .filter(PreguntaEncuesta.id == conversacion.pregunta_actual_id)
            .first()
        )

        if not pregunta:
            raise ValueError("No se pudo obtener la pregunta actual")

        # Enviar la pregunta según su tipo
        if pregunta.tipo_pregunta_id in [3, 4]:  # Selección única o múltiple
            opciones = [op.texto for op in pregunta.opciones]
            await enviar_mensaje_whatsapp(
                chat_id,
                pregunta.texto,
                opciones=opciones,
                tipo_mensaje="lista"  # Usar lista para mostrar opciones
            )
        else:
            await enviar_mensaje_whatsapp(chat_id, pregunta.texto)

        return conversacion

    except Exception as e:
        logger.error(f"Error enviando primera pregunta: {str(e)}")
        raise