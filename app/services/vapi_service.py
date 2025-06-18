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
async def crear_llamada_encuesta(
    db: Session,
    entrega_id: UUID,
    telefono: str,
    nombre_destinatario: str,
    campana_nombre: str,
    preguntas: List[Dict],
):
    """
    Crea una llamada de encuesta utilizando Vapi con un asistente pre-configurado
    """
    try:
        # Inicializar el cliente de Vapi
        client = Vapi(token=settings.VAPI_API_KEY)
        
        # Preparar el número de teléfono para formato E.164
        telefono_limpio = telefono.replace(" ", "")
        if not telefono_limpio.startswith("+"):
            telefono_limpio = f"+{telefono_limpio}"
        
        # Formatear las preguntas para el prompt
        preguntas_formateadas = formatear_preguntas_para_prompt(preguntas)
        
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
                    "preguntas": preguntas_formateadas  # String formateado con todas las preguntas
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

# Función para formatear preguntas para el asistente de Vapi
def formatear_preguntas_para_prompt(preguntas: List[Dict]) -> str:
    """
    Formatea las preguntas para el prompt de Vapi de forma legible
    
    Devuelve un string con el formato adecuado para que el asistente
    pueda leer las preguntas y sus opciones.
    """
    preguntas_formateadas = ""
    
    for i, pregunta in enumerate(preguntas):
        preguntas_formateadas += f"\n## Pregunta {i+1}: {pregunta['texto']}\n"
        preguntas_formateadas += f"(ID: {pregunta['id']}, Tipo: {pregunta['tipo_pregunta_id']})\n"
        
        # Instrucciones específicas según el tipo de pregunta
        if pregunta['tipo_pregunta_id'] == 1:
            preguntas_formateadas += "Tipo: Respuesta abierta (texto)\n"
        elif pregunta['tipo_pregunta_id'] == 2:
            preguntas_formateadas += "Tipo: Respuesta numérica (1-10)\n"
        elif pregunta['tipo_pregunta_id'] == 3:
            preguntas_formateadas += "Tipo: Selección única\n"
        elif pregunta['tipo_pregunta_id'] == 4:
            preguntas_formateadas += "Tipo: Selección múltiple\n"
        
        # Añadir opciones si existen
        if pregunta.get("opciones"):
            preguntas_formateadas += "\nOpciones:\n"
            for j, opcion in enumerate(pregunta["opciones"]):
                letra = chr(65 + j)  # A, B, C, ...
                preguntas_formateadas += f"- {letra}) {opcion['texto']} (ID: {opcion['id']})\n"
        
        preguntas_formateadas += "\n"
    
    return preguntas_formateadas



