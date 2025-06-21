from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from openai import AsyncOpenAI
import re
import json
import logging

# Configure logger
logger = logging.getLogger(__name__)

from app.models.survey import (
    CampanaEncuesta, ConversacionEncuesta, EntregaEncuesta, 
    PlantillaEncuesta, PreguntaEncuesta
)
from app.schemas.conversacion_schema import ConversacionCreate, Mensaje
from app.core.config import settings
from app.services.respuestas_service import crear_respuesta_encuesta
from app.services.shared_service import get_entrega_con_plantilla

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
        if msg.get("role") and msg.get("content"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Agregar contexto sobre el tipo de pregunta
    tipo_contexto = {
        1: "Esta es una pregunta abierta. Sé amable y natural al preguntar.",
        2: "Esta pregunta requiere una respuesta numérica. Pídelo amablemente.",
        3: "Esta pregunta requiere seleccionar una opción específica. Menciona que debe elegir una opción exactamente como está escrita en la lista.",
        4: "Esta pregunta permite seleccionar múltiples opciones. Menciona que puede seleccionar varias opciones separadas por comas, y deben estar escritas exactamente como aparecen en la lista."
    }
    
    messages.append({
        "role": "system",
        "content": f"Necesitas preguntar: '{pregunta_texto}'. {tipo_contexto.get(tipo_pregunta, tipo_contexto[1])}"
    })

    # Llamada a la API
    response = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0.3
    )

    return response.choices[0].message.content


async def analizar_respuesta_con_ai(
    respuesta_usuario: str, 
    opciones: List[str], 
    tipo_pregunta: int
) -> Tuple[Any, str]:
    """
    Analiza la respuesta del usuario con AI para determinar qué opciones ha seleccionado,
    especialmente útil para preguntas tipo 3 y 4 donde el usuario puede no escribir exactamente la opción.
    
    Args:
        respuesta_usuario: Texto de la respuesta del usuario
        opciones: Lista de opciones disponibles
        tipo_pregunta: 3 para selección única, 4 para selección múltiple
    
    Returns:
        Tuple con (valor_procesado, mensaje_error) donde valor_procesado puede ser:
        - Para tipo 3: índice de la opción seleccionada
        - Para tipo 4: lista de índices de las opciones seleccionadas
        Si hay error, valor_procesado será None y mensaje_error contendrá el mensaje de error
    """
    try:
        # Verificar primero si hay una coincidencia exacta (caso feliz)
        if tipo_pregunta == 3:  # Selección única
            for i, opcion in enumerate(opciones):
                if respuesta_usuario.strip().lower() == opcion.lower():
                    return i, ""
                
            # Si llegamos aquí, no hubo coincidencia exacta, usar AI
            prompt = f"""
            La respuesta del usuario es: "{respuesta_usuario}"
            Las opciones disponibles son: {', '.join([f'"{opt}"' for opt in opciones])}
            
            El usuario debe elegir una sola opción. Determina cuál de las opciones quiso seleccionar el usuario.
            Responde SOLO con el índice numérico (0 para la primera opción, 1 para la segunda, etc.)
            Si la selección no es clara, responde "No se pudo determinar la opción".
            """
            
        else:  # Selección múltiple
            # Primero dividir por comas y verificar coincidencias exactas
            selecciones_usuario = [s.strip().lower() for s in respuesta_usuario.split(",")]
            indices_seleccionados = []
            
            for seleccion in selecciones_usuario:
                for i, opcion in enumerate(opciones):
                    if seleccion == opcion.lower():
                        indices_seleccionados.append(i)
            
            if indices_seleccionados:
                return indices_seleccionados, ""
            
            # Si no hay coincidencias exactas, usar AI
            prompt = f"""
            La respuesta del usuario es: "{respuesta_usuario}"
            Las opciones disponibles son: {', '.join([f'"{opt}"' for opt in opciones])}
            
            El usuario puede elegir varias opciones. Determina cuáles opciones quiso seleccionar.
            Responde SOLO con los índices numéricos separados por comas (0 para la primera opción, 1 para la segunda, etc.)
            Si no se puede determinar ninguna selección, responde "No se pudieron determinar las opciones".
            """
        
        # Llamada a la API para análisis
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente que analiza respuestas a encuestas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        # Procesar la respuesta
        resultado = response.choices[0].message.content.strip()
        
        if tipo_pregunta == 3:
            if "no se pudo" in resultado.lower():
                return None, "Por favor, elige una opción exactamente como aparece en la lista."
            
            try:
                indice = int(re.search(r'\d+', resultado).group())
                if 0 <= indice < len(opciones):
                    return indice, ""
                else:
                    return None, "La opción seleccionada no es válida. Por favor, elige una opción de la lista."
            except:
                return None, "No pude identificar tu selección. Por favor, elige una opción exactamente como aparece en la lista."
            
        else:  # tipo 4
            if "no se pudieron" in resultado.lower():
                return None, "No pude identificar las opciones que seleccionaste. Por favor, escribe las opciones exactamente como aparecen en la lista, separadas por comas."
                
            try:
                # Extraer todos los números del texto
                indices = [int(n) for n in re.findall(r'\d+', resultado)]
                # Filtrar índices válidos
                indices_validos = [i for i in indices if 0 <= i < len(opciones)]
                
                if indices_validos:
                    return indices_validos, ""
                else:
                    return None, "Las opciones seleccionadas no son válidas. Por favor, elige opciones de la lista proporcionada."
            except:
                return None, "No pude identificar tus selecciones. Por favor, escribe las opciones exactamente como aparecen en la lista, separadas por comas."
    
    except Exception as e:
        return None, f"Error analizando la respuesta: {str(e)}. Por favor, intenta nuevamente."


async def analizar_respuesta_con_gpt(
    respuesta_usuario: str,
    opciones: List[str],
    pregunta: str
) -> Tuple[int, float]:
    """
    Analiza la respuesta del usuario usando GPT para encontrar la mejor coincidencia.
    
    Returns:
        Tuple[int, float]: (índice de la opción más cercana, nivel de confianza)
    """
    prompt = f"""
    Pregunta: "{pregunta}"
    Respuesta del usuario: "{respuesta_usuario}"
    Opciones disponibles:
    {json.dumps(opciones, indent=2)}
    
    Analiza la respuesta y determina cuál de las opciones disponibles es la más cercana.
    Responde solo con un JSON que contenga:
    - index: índice de la opción más cercana (0 basado)
    - confidence: nivel de confianza entre 0 y 1
    - reasoning: breve explicación de por qué se eligió esa opción
    """
    
    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente que analiza respuestas de encuestas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        result = json.loads(response.choices[0].message.content)
        return result["index"], result["confidence"]
        
    except Exception as e:
        return None, 0.0


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
        raise ValueError(f"Conversación {conversacion_id} no encontrada")
    
    # Si la conversación ya está completada, no procesar más respuestas
    if conversacion.completada:
        return {
            "completada": True,
            "mensaje": "Esta encuesta ya ha sido completada. Gracias por tu participación."
        }

    # Agregar respuesta al historial
    nuevo_mensaje = {"role": "user", "content": respuesta_usuario, "timestamp": datetime.now().isoformat()}
    if not conversacion.historial:
        conversacion.historial = []
    conversacion.historial.append(nuevo_mensaje)

    # Obtener la pregunta actual
    pregunta_actual = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.id == conversacion.pregunta_actual_id)
        .options(joinedload(PreguntaEncuesta.opciones))
        .first()
    )
    
    if not pregunta_actual:
        raise ValueError("Pregunta actual no encontrada")

    # Procesar respuesta según tipo de pregunta
    valor_procesado = None
    
    try:
        if pregunta_actual.tipo_pregunta_id == 1:  # Texto
            # Para preguntas de texto, guardamos el texto directamente
            valor_procesado = respuesta_usuario
            
        elif pregunta_actual.tipo_pregunta_id == 2:  # Número
            # Para preguntas numéricas, intentamos convertir a número
            try:
                valor_procesado = float(respuesta_usuario.strip())
            except ValueError:
                return {"error": "Por favor, ingresa un número válido."}
                
        elif pregunta_actual.tipo_pregunta_id == 3:  # Select (opción única)
            # Verificar si la respuesta es una opción válida
            opciones = [opcion.texto for opcion in pregunta_actual.opciones]
            
            # Primero buscar coincidencia exacta
            opcion_seleccionada = None
            
            for opcion in pregunta_actual.opciones:
                if respuesta_usuario.strip().lower() == opcion.texto.lower():
                    opcion_seleccionada = opcion
                    break
            
            if opcion_seleccionada:
                # Coincidencia exacta encontrada
                valor_procesado = opcion_seleccionada.id
            else:
                # Intentar analizar con AI si no hay coincidencia exacta
                indice_opcion, mensaje_error = await analizar_respuesta_con_ai(
                    respuesta_usuario, opciones, 3
                )
                
                if indice_opcion is not None:
                    opcion_seleccionada = pregunta_actual.opciones[indice_opcion]
                    valor_procesado = opcion_seleccionada.id
                else:
                    # No se pudo identificar la opción
                    opciones_texto = "\n".join([f"• {op.texto}" for op in pregunta_actual.opciones])
                    return {"error": f"{mensaje_error}\n\nOpciones disponibles:\n{opciones_texto}"}
                
        elif pregunta_actual.tipo_pregunta_id == 4:  # Multiselect
            # Para multiselect, el usuario puede seleccionar varias opciones
            opciones = [opcion.texto for opcion in pregunta_actual.opciones]
            
            # Intentar coincidencias exactas primero
            respuestas = [r.strip().lower() for r in respuesta_usuario.split(',')]
            opciones_seleccionadas = []
            todas_coincidencias_exactas = True
            
            for respuesta in respuestas:
                coincidencia_encontrada = False
                for i, opcion in enumerate(pregunta_actual.opciones):
                    if respuesta == opcion.texto.lower():
                        opciones_seleccionadas.append(opcion.id)
                        coincidencia_encontrada = True
                        break
                
                if not coincidencia_encontrada:
                    todas_coincidencias_exactas = False
                    break
                    
            if todas_coincidencias_exactas and opciones_seleccionadas:
                # Todas las respuestas coinciden exactamente con opciones
                valor_procesado = opciones_seleccionadas
            else:
                # Intentar analizar con AI
                indices_opciones, mensaje_error = await analizar_respuesta_con_ai(
                    respuesta_usuario, opciones, 4
                )
                
                if indices_opciones:
                    # Convertir índices a IDs de opciones
                    opciones_seleccionadas = [
                        pregunta_actual.opciones[i].id for i in indices_opciones
                    ]
                    valor_procesado = opciones_seleccionadas
                else:
                    # No se pudieron identificar las opciones
                    opciones_texto = "\n".join([f"• {op.texto}" for op in pregunta_actual.opciones])
                    return {"error": f"{mensaje_error}\n\nOpciones disponibles:\n{opciones_texto}"}

        # Obtener todas las preguntas de la plantilla en orden
        preguntas_plantilla = (
            db.query(PreguntaEncuesta)
            .join(PlantillaEncuesta)
            .join(CampanaEncuesta)
            .join(EntregaEncuesta)
            .filter(EntregaEncuesta.id == conversacion.entrega_id)
            .order_by(PreguntaEncuesta.orden)
            .all()
        )

        # Encontrar la siguiente pregunta en orden
        siguiente_pregunta = None
        for i, pregunta in enumerate(preguntas_plantilla):
            if pregunta.id == pregunta_actual.id and i + 1 < len(preguntas_plantilla):
                siguiente_pregunta = preguntas_plantilla[i + 1]
                break

        if not siguiente_pregunta:
            # Si es la última pregunta
            conversacion.completada = True
            db.commit()
            
            # Crear respuesta final
            try:
                respuesta = await crear_respuesta_encuesta(
                    db, 
                    conversacion.entrega_id,
                    conversacion.historial
                )
                
                return {
                    "completada": True,
                    "mensaje": "¡Gracias por completar la encuesta!",
                    "respuesta_id": str(respuesta.id)
                }
            except Exception as e:
                logger.error(f"Error guardando respuesta final: {str(e)}")
                raise ValueError(f"Error guardando respuesta: {str(e)}")

        # Si hay siguiente pregunta...
        # ... resto del código para siguiente pregunta ...
        
    except Exception as e:
        logger.error(f"Error procesando respuesta: {str(e)}")
        raise