from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel
from decimal import Decimal

class OpcionInResponse(BaseModel):
    id: UUID
    texto: str
    valor: Optional[str] = None

    model_config = {"from_attributes": True}

class PreguntaInResponse(BaseModel):
    id: UUID
    orden: int
    texto: str
    tipo_pregunta_id: int
    obligatorio: bool
    opciones: List[OpcionInResponse] = []

    model_config = {"from_attributes": True}

class PlantillaInResponse(BaseModel):
    id: UUID
    nombre: str
    descripcion: Optional[str] = None
    preguntas: List[PreguntaInResponse] = []

    model_config = {"from_attributes": True}

class RespuestaPreguntaInResponse(BaseModel):
    id: UUID
    pregunta_id: UUID
    texto: Optional[str] = None
    numero: Optional[Decimal] = None
    opcion_id: Optional[UUID] = None
    metadatos: dict = {}

    model_config = {"from_attributes": True}

class RespuestaInResponse(BaseModel):
    id: UUID
    entrega_id: UUID
    puntuacion: Optional[Decimal] = None
    recibido_en: datetime
    respuestas_preguntas: List[RespuestaPreguntaInResponse] = []

    model_config = {"from_attributes": True}

class DestinarioInResponse(BaseModel):
    id: UUID
    nombre: str
    telefono: Optional[str] = None
    email: Optional[str] = None

    model_config = {"from_attributes": True}

class EntregaInResponse(BaseModel):
    id: UUID
    estado_id: int
    enviado_en: Optional[datetime] = None
    respondido_en: Optional[datetime] = None
    destinatario: DestinarioInResponse
    respuestas: List[RespuestaInResponse] = []

    model_config = {"from_attributes": True}

class CampanaBase(BaseModel):
    nombre: str
    plantilla_id: Optional[UUID]
    canal_id: int
    programada_en: Optional[datetime] = None

class CampanaCreate(CampanaBase):
    pass

class CampanaUpdate(BaseModel):
    nombre: Optional[str] = None
    plantilla_id: Optional[UUID] = None
    canal_id: Optional[int] = None
    programada_en: Optional[datetime] = None
    estado_id: Optional[int] = None  # Permitimos actualizar el estado directamente

class CampanaOut(CampanaBase):
    id: UUID
    suscriptor_id: UUID
    estado_id: int
    creado_en: datetime

    model_config = {"from_attributes": True}

# Para respuestas detalladas que incluyen info de la plantilla
class CampanaDetailOut(CampanaOut):
    plantilla: Optional[dict] = None  # Simplificado por ahora
    entregas_count: Optional[int] = None

class CampanaFullDetailOut(BaseModel):
    id: UUID
    suscriptor_id: UUID
    nombre: str
    plantilla_id: Optional[UUID]
    canal_id: int
    programada_en: Optional[datetime]
    estado_id: int
    creado_en: datetime
    
    # Relaciones detalladas
    plantilla: Optional[PlantillaInResponse]
    entregas: List[EntregaInResponse] = []
    total_entregas: int = 0
    total_respondidas: int = 0
    total_pendientes: int = 0

    model_config = {"from_attributes": True}