# app/services/vapi_service.py
from __future__ import annotations

from typing import List, Dict, Any
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from vapi import Vapi

from app.core.config import settings
from app.models.survey import VapiCallRelation



# ──────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
# Función para formatear las preguntas exactamente como están, sin agregar contenido
def formatear_preguntas_para_prompt(preguntas: List[Dict]) -> str:
    """
    Formatea las preguntas incluyendo TODOS los datos técnicos necesarios
    para que el asistente pueda construir la respuesta estructurada correctamente.
    """
    preguntas_formateadas = ""
    
    for i, pregunta in enumerate(preguntas):
        preguntas_formateadas += f"\n--- PREGUNTA {i+1} ---\n"
        preguntas_formateadas += f"Texto: {pregunta['texto']}\n"
        preguntas_formateadas += f"pregunta_id: {pregunta['id']}\n"
        preguntas_formateadas += f"tipo_pregunta_id: {pregunta['tipo_pregunta_id']}\n"
        
        # Añadir instrucciones según el tipo de pregunta
        if pregunta['tipo_pregunta_id'] == 1:  # Texto
            preguntas_formateadas += "Instrucción: Captura respuesta en formato texto\n"
        elif pregunta['tipo_pregunta_id'] == 2:  # Número
            preguntas_formateadas += "Instrucción: Captura respuesta numérica (1-10)\n"
        elif pregunta['tipo_pregunta_id'] == 3:  # Selección única
            preguntas_formateadas += "Instrucción: Captura una sola opción. Usa el opcion_id exacto de la opción seleccionada\n"
        elif pregunta['tipo_pregunta_id'] == 4:  # Selección múltiple
            preguntas_formateadas += "Instrucción: Captura múltiples opciones. Usa los opcion_id exactos de las opciones seleccionadas\n"
        
        # Añadir opciones si existen con TODOS sus datos
        if pregunta.get("opciones"):
            preguntas_formateadas += "\nOpciones disponibles:\n"
            for j, opcion in enumerate(pregunta["opciones"]):
                letra = chr(65 + j)  # A, B, C, ...
                preguntas_formateadas += f"- Opción {letra}: {opcion['texto']}\n"
                preguntas_formateadas += f"  opcion_id: {opcion['id']}\n"
        
        preguntas_formateadas += "\n"
    
    # Agregar instrucciones explícitas para la construcción de la respuesta
    preguntas_formateadas += "\n--- INSTRUCCIONES PARA ESTRUCTURAR LA RESPUESTA ---\n"
    preguntas_formateadas += "1. Para cada pregunta, DEBES incluir todos estos campos en tu respuesta estructurada:\n"
    preguntas_formateadas += "   - pregunta_id: Exactamente como se te proporcionó\n"
    preguntas_formateadas += "   - tipo_pregunta_id: El número del tipo de pregunta\n"
    preguntas_formateadas += "   - Para preguntas tipo 1: Incluye 'texto' con la respuesta\n"
    preguntas_formateadas += "   - Para preguntas tipo 2: Incluye 'numero' con el valor numérico\n"
    preguntas_formateadas += "   - Para preguntas tipo 3: Incluye 'opcion_id' con el ID exacto de la opción seleccionada\n"
    preguntas_formateadas += "   - Para preguntas tipo 4: Incluye 'opcion_id' como array de IDs de las opciones seleccionadas\n"
    preguntas_formateadas += "2. Calcula la puntuación promedio de todas las respuestas numéricas\n"
    
    return preguntas_formateadas


async def crear_llamada_encuesta(
    db: Session,
    entrega_id: UUID,
    telefono: str,
    nombre_destinatario: str,
    campana_nombre: str,
    preguntas: List[Dict],
):
    """
    Crea una llamada de encuesta utilizando Vapi con un asistente pre-configurado,
    asegurando que se pasen TODOS los datos necesarios para las respuestas.
    """
    try:
        # Inicializar el cliente de Vapi
        client = Vapi(token=settings.VAPI_API_KEY)
        
        # Preparar el número de teléfono para formato E.164
        telefono_limpio = telefono.replace(" ", "")
        if not telefono_limpio.startswith("+"):
            telefono_limpio = f"+{telefono_limpio}"
        
        # Formatear las preguntas con TODOS los datos técnicos necesarios
        preguntas_detalladas = formatear_preguntas_para_prompt(preguntas)
        
        # Crear la llamada usando el ID de asistente pre-configurado
        call = client.calls.create(
            phone_number_id=settings.VAPI_PHONE_NUMBER_ID,
            assistant_id=settings.VAPI_ASSISTANT_ID,
            customer={
                "number": telefono_limpio,
                "name": nombre_destinatario
            },
            assistant_overrides={
                "variableValues": {
                    "nombre": nombre_destinatario,
                    "campana": campana_nombre,
                    "preguntas": preguntas_detalladas
                },
                "voice_settings": {
                    "volume": 2.0,              # Aumenta el volumen
                    "use_speaker_boost": True   # Mejora la claridad
                },
                "recognition_settings": {
                    "endpointing": "aggressive",  # Detección más agresiva del fin del habla
                    "boost": 1.3,                 # Amplifica la señal de entrada
                    "sensitivity": "high",        # Mayor sensibilidad a la voz humana
                    "energy_threshold": 0.4,      # Umbral más bajo para detectar voz
                    "timeout_seconds": 3.0        # Espera más tiempo para respuestas
                }
            }
        )
        
        # Guardar la relación call_id ↔ entrega_id
        relation = VapiCallRelation(
            entrega_id=entrega_id, 
            call_id=call.id
        )
        db.add(relation)
        db.commit()
        
        return {
            "call_id": call.id,
            "status": call.status
        }
            
    except Exception as e:
        print(f"Error al crear llamada Vapi: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando llamada con Vapi: {str(e)}"
        )



