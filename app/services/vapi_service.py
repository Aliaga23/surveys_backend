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
    Formatea las preguntas exactamente como están en la base de datos
    para el prompt de Vapi, manteniendo los IDs originales.
    """
    preguntas_formateadas = ""
    
    for i, pregunta in enumerate(preguntas):
        # Mostrar la pregunta exactamente como está, con su ID original
        preguntas_formateadas += f"\n## Pregunta {i+1}: {pregunta['texto']}\n"
        preguntas_formateadas += f"ID: {pregunta['id']}\n"
        preguntas_formateadas += f"Tipo: {pregunta['tipo_pregunta_id']}\n"
        
        # Añadir opciones si existen, manteniendo sus IDs exactos
        if pregunta.get("opciones"):
            preguntas_formateadas += "Opciones:\n"
            for j, opcion in enumerate(pregunta["opciones"]):
                preguntas_formateadas += f"- {opcion['texto']} (ID: {opcion['id']})\n"
        
        preguntas_formateadas += "\n"
    
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
    Crea una llamada de encuesta utilizando Vapi con un asistente pre-configurado
    """
    try:
        # Inicializar el cliente de Vapi
        client = Vapi(token=settings.VAPI_API_KEY)
        
        # Preparar el número de teléfono para formato E.164
        telefono_limpio = telefono.replace(" ", "")
        if not telefono_limpio.startswith("+"):
            telefono_limpio = f"+{telefono_limpio}"
        
        # Formatear las preguntas para el prompt - manteniéndolas exactas
        preguntas_exactas = formatear_preguntas_para_prompt(preguntas)
        
        # También pasar las preguntas estructuradas para que la IA tenga acceso directo
        preguntas_estructuradas = []
        for pregunta in preguntas:
            pregunta_estructurada = {
                "id": str(pregunta["id"]),
                "texto": pregunta["texto"],
                "tipo": pregunta["tipo_pregunta_id"]
            }
            
            if pregunta.get("opciones"):
                pregunta_estructurada["opciones"] = [
                    {"id": str(opcion["id"]), "texto": opcion["texto"]}
                    for opcion in pregunta["opciones"]
                ]
                
            preguntas_estructuradas.append(pregunta_estructurada)
        
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
                    "preguntas": preguntas_exactas,
                    "preguntas_json": preguntas_estructuradas  # Datos estructurados para referencia
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



