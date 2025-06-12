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
    puntuacion: Optional[Decimal] = None
    raw_payload: Optional[dict] = None

class RespuestaEncuestaCreate(RespuestaEncuestaBase):
    respuestas_preguntas: List[RespuestaPreguntaCreate]

class RespuestaEncuestaUpdate(BaseModel):
    puntuacion: Optional[Decimal] = None

class RespuestaEncuestaOut(RespuestaEncuestaBase):
    id: UUID
    entrega_id: UUID
    recibido_en: datetime
    respuestas_preguntas: List[RespuestaPreguntaOut] = []

    model_config = {"from_attributes": True}