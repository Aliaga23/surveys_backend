from datetime import datetime
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel


# ────────────────────── auxiliares: plantilla/preguntas ──────────────────
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


# ────────────────────── auxiliares: respuestas ───────────────────────────
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
    recibido_en: datetime
    respuestas_preguntas: List[RespuestaPreguntaInResponse] = []

    model_config = {"from_attributes": True}


# ────────────────────── destinatario (ahora opcional) ────────────────────
class DestinatarioInResponse(BaseModel):
    id: Optional[UUID] = None
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None

    model_config = {"from_attributes": True}


# ────────────────────── entrega (con destinatario opcional) ──────────────
class EntregaInResponse(BaseModel):
    id: UUID
    estado_id: int
    enviado_en: Optional[datetime] = None
    respondido_en: Optional[datetime] = None
    destinatario: Optional[DestinatarioInResponse] = None   # ← aquí el cambio
    respuestas: List[RespuestaInResponse] = []

    model_config = {"from_attributes": True}


# ────────────────────── objetos de campaña (CRUD) ────────────────────────
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
    estado_id: Optional[int] = None   # permitir actualizar estado directamente


class CampanaOut(CampanaBase):
    id: UUID
    suscriptor_id: UUID
    estado_id: int
    creado_en: datetime

    model_config = {"from_attributes": True}


# Detalle simple (contiene solo counts y plantilla simplificada)
class CampanaDetailOut(CampanaOut):
    plantilla: Optional[dict] = None
    entregas_count: Optional[int] = None


# Detalle completo con relaciones anidadas
class CampanaFullDetailOut(BaseModel):
    id: UUID
    suscriptor_id: UUID
    nombre: str
    plantilla_id: Optional[UUID]
    canal_id: int
    programada_en: Optional[datetime]
    estado_id: int
    creado_en: datetime

    plantilla: Optional[PlantillaInResponse] = None
    entregas: List[EntregaInResponse] = []          # ← EntregaInResponse ya ajustada
    total_entregas: int = 0
    total_respondidas: int = 0
    total_pendientes: int = 0

    model_config = {"from_attributes": True}
