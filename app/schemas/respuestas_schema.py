from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, constr
from decimal import Decimal

class RespuestaPreguntaBase(BaseModel):
    pregunta_id: UUID
    texto: Optional[str] = None
    numero: Optional[Decimal] = None
    opcion_id: Optional[UUID] = None
    metadatos: dict = {}

class RespuestaPreguntaCreate(RespuestaPreguntaBase):
    pass

class RespuestaPreguntaOut(RespuestaPreguntaBase):
    id: UUID
    respuesta_id: UUID

    model_config = {"from_attributes": True}

class RespuestaEncuestaBase(BaseModel):
    raw_payload: Optional[dict] = None

class RespuestaEncuestaCreate(RespuestaEncuestaBase):
    respuestas_preguntas: List[RespuestaPreguntaCreate]

class RespuestaEncuestaUpdate(BaseModel):
    pass  # Mantén 'pass' si no quedan otros campos

class RespuestaEncuestaOut(RespuestaEncuestaBase):
    id: UUID
    entrega_id: UUID
    recibido_en: datetime
    respuestas_preguntas: List[RespuestaPreguntaOut] = []

    model_config = {"from_attributes": True}

class RespuestaCreateEmail(BaseModel):
    """Esquema para crear respuestas desde el enlace de email"""
    pregunta_id: str
    tipo_respuesta: str  # "texto", "numero", "opcion", "opciones"
    texto: Optional[str] = None
    numero: Optional[float] = None
    opcion_id: Optional[str] = None
    opciones_ids: Optional[List[str]] = None