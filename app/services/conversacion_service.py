from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
from openai import AsyncOpenAI
from thefuzz import fuzz

from app.models.survey import CampanaEncuesta, ConversacionEncuesta, EntregaEncuesta, PlantillaEncuesta, PreguntaEncuesta
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
        3: "Esta pregunta requiere seleccionar una opción específica. Menciona que debe elegir una opción pero no enumeres las opciones.",
        4: "Esta pregunta permite seleccionar múltiples opciones. Menciona que puede seleccionar varias opciones pero no las enumeres."
    }
    
    messages.append({
        "role": "system",
        "content": f"Necesitas preguntar: '{pregunta_texto}'. {tipo_contexto[tipo_pregunta]}"
    })

    response = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0.7
    )

    return response.choices[0].message.content

async def procesar_respuesta(
    db: Session,
    conversacion_id: UUID,
    respuesta_usuario: str
) -> Dict:
    """Procesa la respuesta del usuario y determina la siguiente acción"""
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

    # Agregar respuesta al historial
    nuevo_mensaje = {"role": "user", "content": respuesta_usuario, "timestamp": datetime.now().isoformat()}
    if not conversacion.historial:
        conversacion.historial = []
    conversacion.historial.append(nuevo_mensaje)

    # Obtener la pregunta actual y todas las preguntas de la plantilla
    pregunta_actual = conversacion.pregunta_actual
    preguntas_plantilla = (
        db.query(PreguntaEncuesta)
        .filter(
            PreguntaEncuesta.plantilla_id == conversacion.entrega.campana.plantilla_id
        )
        .order_by(PreguntaEncuesta.orden)
        .all()
    )
    
    # Procesar la respuesta según el tipo de pregunta
    valor_procesado = None
    if pregunta_actual.tipo_pregunta_id == 1:  # Texto
        valor_procesado = respuesta_usuario
    elif pregunta_actual.tipo_pregunta_id == 2:  # Número
        try:
            valor_procesado = float(respuesta_usuario)
            if not (1 <= valor_procesado <= 10):
                return {"error": "Por favor, ingresa un número entre 1 y 10"}
        except ValueError:
            return {"error": "Por favor, ingresa un número válido"}
    elif pregunta_actual.tipo_pregunta_id == 3:  # Select
        # Validar que la respuesta coincida con alguna opción
        mejor_coincidencia = None
        mejor_score = 0
        for opcion in pregunta_actual.opciones:
            score = fuzz.ratio(respuesta_usuario.lower(), opcion.texto.lower())
            if score > mejor_score:
                mejor_score = score
                mejor_coincidencia = opcion
        
        if mejor_score < 70:
            opciones_texto = "\n".join([f"- {op.texto}" for op in pregunta_actual.opciones])
            return {"error": f"Por favor, elige una de las siguientes opciones:\n{opciones_texto}"}
        valor_procesado = mejor_coincidencia.id
    elif pregunta_actual.tipo_pregunta_id == 4:  # Multiselect
        # Implementar lógica para multiselect
        pass

    # Encontrar la siguiente pregunta en orden
    siguiente_pregunta = None
    for i, pregunta in enumerate(preguntas_plantilla):
        if pregunta.id == pregunta_actual.id and i + 1 < len(preguntas_plantilla):
            siguiente_pregunta = preguntas_plantilla[i + 1]
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
        
        db.commit()
        
        return {
            "valor_procesado": valor_procesado,
            "siguiente_pregunta": texto_siguiente,
            "tipo_pregunta": siguiente_pregunta.tipo_pregunta_id,
            "opciones": opciones,
            "completada": False
        }
    else:
        # Encuesta completada
        conversacion.completada = True
        db.commit()
        
        # Crear la respuesta final
        await crear_respuesta_encuesta(db, conversacion.entrega_id, conversacion.historial)
        
        return {
            "valor_procesado": valor_procesado,
            "siguiente_pregunta": "¡Gracias por completar la encuesta!",
            "completada": True
        }