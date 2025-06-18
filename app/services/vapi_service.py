from vapi import Vapi
from typing import List, Dict, Any
from fastapi import HTTPException, status
from uuid import UUID
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.survey import VapiCallRelation


async def crear_llamada_encuesta(
    db: Session,
    entrega_id: UUID,
    telefono: str,
    nombre_destinatario: str,
    campana_nombre: str,
    preguntas: List[Dict],
):
    """
    Crea una llamada de encuesta utilizando Vapi
    
    Parámetros:
    - db: Sesión de base de datos
    - entrega_id: ID de la entrega
    - telefono: Número de teléfono del destinatario
    - nombre_destinatario: Nombre del destinatario para personalizar
    - campana_nombre: Nombre de la campaña para contextualizar
    - preguntas: Lista de preguntas con sus opciones
    """
    try:
        # Inicializar el cliente de Vapi
        client = Vapi(token=settings.VAPI_API_KEY)
        
        # Preparar el número de teléfono para formato E.164
        telefono_limpio = telefono.replace(" ", "")
        # Asegurar que tenga prefijo +
        if not telefono_limpio.startswith("+"):
            telefono_limpio = f"+{telefono_limpio}"
        
        # Construir el contexto para el asistente con las preguntas
        contexto = (
            "Eres un asistente profesional realizando una encuesta telefónica.\n\n"
            "Tu objetivo es obtener respuestas claras a las siguientes preguntas:\n\n"
        )
        
        # Esquema de datos estructurados para análisis
        schema = {
            "type": "object",
            "properties": {
                "puntuacion": {"type": "number"},
                "respuestas_preguntas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pregunta_id": {"type": "string"},
                            "tipo_pregunta_id": {"type": "integer"},
                            "texto": {"type": "string"},
                            "numero": {"type": "number"},
                            "opcion_id": {"type": "string"},
                        },
                        "required": ["pregunta_id", "tipo_pregunta_id"]
                    }
                }
            },
            "required": ["respuestas_preguntas"]
        }
        
        # Añadir cada pregunta al contexto
        for i, pregunta in enumerate(preguntas):
            contexto += f"Pregunta {i+1}: {pregunta['texto']}\n"
            contexto += f"ID de la pregunta: {pregunta['id']} (no menciones este ID al usuario)\n"
            contexto += f"Tipo de pregunta: {pregunta['tipo_pregunta_id']}\n"
            
            # Si tiene opciones, incluirlas
            if pregunta.get("opciones"):
                contexto += "Opciones:\n"
                for j, opcion in enumerate(pregunta["opciones"]):
                    letra = chr(65 + j)  # A, B, C, ...
                    contexto += f"   {letra}) {opcion['texto']} (ID: {opcion['id']} - no mencionar)\n"
                
                # Instrucciones específicas para preguntas de opción
                if pregunta["tipo_pregunta_id"] == 3:  # Select
                    contexto += "Para esta pregunta, el usuario debe elegir UNA opción. Registra el ID de la opción elegida.\n"
                elif pregunta["tipo_pregunta_id"] == 4:  # Multiselect
                    contexto += "Para esta pregunta, el usuario puede elegir VARIAS opciones. Registra los IDs de todas las opciones elegidas.\n"
            
            # Instrucciones según tipo de pregunta
            if pregunta["tipo_pregunta_id"] == 1:  # Texto
                contexto += "Esta es una pregunta de TEXTO. Registra la respuesta completa del usuario.\n"
            elif pregunta["tipo_pregunta_id"] == 2:  # Número
                contexto += "Esta es una pregunta NUMÉRICA. Registra solo el número como respuesta (ej. 8).\n"
                
            contexto += "\n"
        
        # Añadir instrucciones para extracción de datos
        contexto += "\nIMPORTANTE para análisis estructurado:\n"
        contexto += "1. Para cada pregunta, extrae la información en el formato adecuado según su tipo.\n"
        contexto += "2. Asegúrate de incluir el ID exacto de cada pregunta y opción.\n"
        contexto += "3. Para preguntas numéricas, extrae solo el número.\n"
        contexto += "4. Para preguntas de selección, extrae el ID de la opción seleccionada.\n"
        
        # Definir el asistente transitorio con los valores corregidos
        assistant = {
            "firstMessage": (
                "Hola {{nombre}}, soy un asistente realizando una encuesta "
                "sobre {{campana}}. ¿Tienes unos minutos?"
            ),
            "context": contexto,
            "analysisPlan": {"structuredDataSchema": schema},
            "voice": "azure:es-ES-AlvaroNeural",      # Voz en español corregida
            "model": "gpt-4o-mini-cluster"            # Modelo corregido
        }
        
        # Crear la llamada usando el cliente oficial
        call = client.calls.create(
            phone_number_id=settings.VAPI_PHONE_NUMBER_ID,
            assistant=assistant,
            customer={"number": telefono_limpio, "name": nombre_destinatario},
            assistant_overrides={
                "variableValues": {
                    "nombre": nombre_destinatario,
                    "campana": campana_nombre
                }
            }
        )
        
        # Guardar la relación call_id ↔ entrega_id
        relation = VapiCallRelation(entrega_id=entrega_id, call_id=call.id)
        db.add(relation)
        db.commit()
        
        return {"call_id": call.id, "status": call.status}
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando llamada con Vapi: {str(e)}"
        )

