from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from openai import AsyncOpenAI
from thefuzz import fuzz

from app.models.survey import CampanaEncuesta, ConversacionEncuesta, EntregaEncuesta, PlantillaEncuesta, PreguntaEncuesta, RespuestaTemp
from app.schemas.conversacion_schema import ConversacionCreate, Mensaje
from app.core.config import settings
from app.services.respuestas_service import crear_respuesta_encuesta
from app.services.shared_service import get_entrega_con_plantilla
from app.services.whatsapp_service import enviar_mensaje_whatsapp

# Initialize the client
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = """
Eres un asistente amigable realizando una encuesta. Tu objetivo es obtener respuestas 
para las preguntas de la encuesta de manera natural y conversacional.
Debes adaptar la siguiente pregunta al contexto de la conversación.
Mantén un tono amigable y empático, pero enfócate en obtener la información necesaria.
"""

async def generar_siguiente_pregunta(
    historial: List[Dict],
    pregunta_texto: str,
    tipo_pregunta: int
) -> str:
    """Genera la siguiente pregunta usando GPT de manera conversacional"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Agregar historial de conversación
    for msg in historial:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Agregar contexto sobre el tipo de pregunta
    tipo_contexto = {
        1: "Esta es una pregunta abierta. Sé amable y natural al preguntar.",
        2: "Esta pregunta requiere una respuesta numérica del 1 al 10. Pídelo amablemente.",
        3: "Esta pregunta requiere seleccionar una opción específica. Menciona que debe elegir una opción pero solo una",
        4: "Esta pregunta permite seleccionar múltiples opciones. Menciona que puede seleccionar varias opciones pero no las enumeres."
    }
    
    messages.append({
        "role": "system",
        "content": f"Necesitas preguntar: '{pregunta_texto}'. {tipo_contexto[tipo_pregunta]}"
    })

    response = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0.3
    )

    return response.choices[0].message.content

async def procesar_respuesta(
    db: Session,
    conversacion_id: UUID,
    respuesta_usuario: str
) -> Dict:
    """Procesa la respuesta del usuario y determina la siguiente acción"""
    print(f"Procesando respuesta para conversación {conversacion_id}: {respuesta_usuario[:30]}...")
    
    conversacion = (
        db.query(ConversacionEncuesta)
        .join(EntregaEncuesta)
        .join(EntregaEncuesta.campana)
        .join(CampanaEncuesta.plantilla)
        .join(PlantillaEncuesta.preguntas)
        .filter(ConversacionEncuesta.id == conversacion_id)
        .first()
    )
    
    if not conversacion:
        raise ValueError("Conversación no encontrada")
    
    # Si la conversación ya está completada, no procesar más respuestas
    if conversacion.completada:
        print(f"La conversación {conversacion_id} ya está completada")
        return {
            "completada": True,
            "mensaje": "Esta encuesta ya ha sido completada. Gracias por tu participación."
        }

    # Agregar respuesta al historial
    nuevo_mensaje = {"role": "user", "content": respuesta_usuario, "timestamp": datetime.now().isoformat()}
    if not conversacion.historial:
        conversacion.historial = []
    conversacion.historial.append(nuevo_mensaje)

    # Obtener la pregunta actual y todas las preguntas de la plantilla
    pregunta_actual = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.id == conversacion.pregunta_actual_id)
        .options(joinedload(PreguntaEncuesta.opciones))
        .first()
    )
    
    if not pregunta_actual:
        raise ValueError("Pregunta actual no encontrada")
    
    print(f"Pregunta actual: {pregunta_actual.texto[:30]}...")

    preguntas_plantilla = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.plantilla_id == pregunta_actual.plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .options(joinedload(PreguntaEncuesta.opciones))
        .all()
    )
    
    print(f"Total de preguntas en plantilla: {len(preguntas_plantilla)}")

    # Procesamiento de la respuesta según el tipo de pregunta
    valor_procesado = None
    if pregunta_actual.tipo_pregunta_id == 1:  # Texto
        valor_procesado = respuesta_usuario
        print(f"Respuesta procesada como TEXTO")
    elif pregunta_actual.tipo_pregunta_id == 2:  # Número
        try:
            valor_procesado = float(respuesta_usuario.strip())
            print(f"Respuesta procesada como NÚMERO: {valor_procesado}")
        except ValueError:
            print(f"Error: respuesta no es un número válido")
            return {"error": "Por favor, ingresa un número válido"}
    elif pregunta_actual.tipo_pregunta_id == 3:  # Select (opción única)
        # Verificar si la respuesta es una opción válida
        opcion_seleccionada = None
        print(f"Opciones disponibles para pregunta {pregunta_actual.texto[:30]}:")
        for opcion in pregunta_actual.opciones:
            print(f"  - {opcion.texto}")
            if respuesta_usuario.strip() == opcion.texto:
                opcion_seleccionada = opcion
        
        if not opcion_seleccionada:
            opciones_texto = "\n".join([f"- {op.texto}" for op in pregunta_actual.opciones])
            print(f"Error: opción no válida")
            return {"error": f"Por favor, elige exactamente una de estas opciones:\n{opciones_texto}"}
        
        valor_procesado = opcion_seleccionada.id
        print(f"Respuesta procesada como OPCIÓN: {opcion_seleccionada.texto} (ID: {valor_procesado})")
    elif pregunta_actual.tipo_pregunta_id == 4:  # Multiselect
        # Para multiselect, el usuario puede seleccionar varias opciones
        opciones_seleccionadas = []
        respuestas = [r.strip() for r in respuesta_usuario.split(',')]
        
        print(f"Opciones indicadas: {respuestas}")
        print(f"Opciones disponibles para pregunta {pregunta_actual.texto[:30]}:")
        for opcion in pregunta_actual.opciones:
            print(f"  - {opcion.texto}")
        
        for respuesta in respuestas:
            opcion_valida = False
            for opcion in pregunta_actual.opciones:
                if respuesta == opcion.texto:
                    opciones_seleccionadas.append(opcion.id)
                    opcion_valida = True
                    print(f"Opción válida encontrada: {opcion.texto}")
                    break
                    
            if not opcion_valida:
                print(f"Error: '{respuesta}' no es una opción válida")
                return {"error": f"'{respuesta}' no es una opción válida para esta pregunta"}
        
        if not opciones_seleccionadas:
            opciones_texto = "\n".join([f"- {op.texto}" for op in pregunta_actual.opciones])
            print(f"Error: no se seleccionó ninguna opción válida")
            return {"error": f"Por favor, elige una o más opciones separadas por comas:\n{opciones_texto}"}
        
        valor_procesado = opciones_seleccionadas
        print(f"Respuesta procesada como OPCIONES MÚLTIPLES: {opciones_seleccionadas}")

    # Encontrar la siguiente pregunta en orden
    siguiente_pregunta = None
    for i, pregunta in enumerate(preguntas_plantilla):
        if pregunta.id == pregunta_actual.id and i + 1 < len(preguntas_plantilla):
            siguiente_pregunta = preguntas_plantilla[i + 1]
            print(f"Siguiente pregunta: {siguiente_pregunta.texto[:30]}...")
            break
    
    if siguiente_pregunta:
        # Generar texto de la siguiente pregunta
        texto_siguiente = await generar_siguiente_pregunta(
            conversacion.historial,
            siguiente_pregunta.texto,
            siguiente_pregunta.tipo_pregunta_id
        )
        
        # Actualizar estado
        conversacion.pregunta_actual_id = siguiente_pregunta.id
        nuevo_mensaje = {"role": "assistant", "content": texto_siguiente, "timestamp": datetime.now().isoformat()}
        conversacion.historial.append(nuevo_mensaje)
        
        # Determinar si hay opciones para enviar
        opciones = None
        if siguiente_pregunta.tipo_pregunta_id in [3, 4]:
            opciones = [opcion.texto for opcion in siguiente_pregunta.opciones]
            print(f"Opciones para enviar: {opciones}")
        
        db.commit()
        print("Estado actualizado, pasando a siguiente pregunta")
        
        return {
            "valor_procesado": valor_procesado,
            "siguiente_pregunta": texto_siguiente,
            "tipo_pregunta": siguiente_pregunta.tipo_pregunta_id,
            "opciones": opciones,
            "completada": False
        }
    else:
        # Encuesta completada
        print("Encuesta completada, procesando respuestas finales")
        conversacion.completada = True
        db.commit()
        
        # Crear la respuesta final con todas las respuestas acumuladas
        respuesta = await crear_respuesta_encuesta(db, conversacion.entrega_id, conversacion.historial)
        
        return {
            "valor_procesado": valor_procesado,
            "siguiente_pregunta": "¡Gracias por completar la encuesta!",
            "completada": True,
            "respuesta_id": str(respuesta.id)
        }

async def guardar_respuesta_individual(
    db: Session,
    entrega_id: UUID,
    pregunta_id: UUID,
    tipo_pregunta_id: int,
    valor_procesado: Any
) -> None:
    """
    Guarda una respuesta individual en la tabla temporal de respuestas
    o la actualiza si ya existe para la misma entrega y pregunta
    """
    # Buscar si ya existe una respuesta para esta pregunta y entrega
    respuesta_existente = (
        db.query(RespuestaTemp)
        .filter(
            RespuestaTemp.entrega_id == entrega_id,
            RespuestaTemp.pregunta_id == pregunta_id
        )
        .first()
    )
    
    # Si existe, actualizar
    if respuesta_existente:
        if tipo_pregunta_id == 1:  # Texto
            respuesta_existente.texto = valor_procesado
        elif tipo_pregunta_id == 2:  # Número
            respuesta_existente.numero = valor_procesado
        elif tipo_pregunta_id == 3:  # Select
            respuesta_existente.opcion_id = valor_procesado
        elif tipo_pregunta_id == 4:  # Multiselect
            # Para multiselect, borramos las respuestas anteriores y creamos nuevas
            db.query(RespuestaTemp).filter(
                RespuestaTemp.entrega_id == entrega_id,
                RespuestaTemp.pregunta_id == pregunta_id
            ).delete()
            
            for opcion_id in valor_procesado:
                nueva_respuesta = RespuestaTemp(
                    entrega_id=entrega_id,
                    pregunta_id=pregunta_id,
                    opcion_id=opcion_id
                )
                db.add(nueva_respuesta)
    else:
        # Si no existe, crear nueva respuesta
        if tipo_pregunta_id in [1, 2, 3]:  # Texto, Número o Select
            nueva_respuesta = RespuestaTemp(
                entrega_id=entrega_id,
                pregunta_id=pregunta_id,
                texto=valor_procesado if tipo_pregunta_id == 1 else None,
                numero=valor_procesado if tipo_pregunta_id == 2 else None,
                opcion_id=valor_procesado if tipo_pregunta_id == 3 else None
            )
            db.add(nueva_respuesta)
        elif tipo_pregunta_id == 4:  # Multiselect
            for opcion_id in valor_procesado:
                nueva_respuesta = RespuestaTemp(
                    entrega_id=entrega_id,
                    pregunta_id=pregunta_id,
                    opcion_id=opcion_id
                )
                db.add(nueva_respuesta)
    
    db.commit()