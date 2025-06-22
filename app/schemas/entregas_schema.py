from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel

# ───────── modelos auxiliares ────────────────────────────────────────────

class OpcionPublicaOut(BaseModel):
    id: UUID
    texto: str
    valor: Optional[str] = None
    model_config = {"from_attributes": True}

class PreguntaPublicaOut(BaseModel):
    id: UUID
    orden: int
    texto: str
    tipo_pregunta_id: int
    obligatorio: bool
    opciones: List[OpcionPublicaOut] = []
    model_config = {"from_attributes": True}

class PlantillaPublicaOut(BaseModel):
    id: UUID
    nombre: str
    descripcion: Optional[str] = None
    preguntas: List[PreguntaPublicaOut] = []
    model_config = {"from_attributes": True}

class DestinatarioPublicoOut(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    model_config = {"from_attributes": True}


class EntregaPublicaOut(BaseModel):
    id: UUID
    plantilla: PlantillaPublicaOut
    destinatario: Optional[DestinatarioPublicoOut] = None   # ← opcional
    model_config = {"from_attributes": True}


class EntregaBase(BaseModel):
    destinatario_id: Optional[UUID] = None
    canal_id: int

class EntregaCreate(EntregaBase):
    pass

class EntregaUpdate(BaseModel):
    estado_id: Optional[int] = None
    enviado_en: Optional[datetime] = None
    respondido_en: Optional[datetime] = None

class EntregaOut(EntregaBase):
    id: UUID
    campana_id: UUID
    estado_id: int
    enviado_en: Optional[datetime] = None
    respondido_en: Optional[datetime] = None
    destinatario: Optional[DestinatarioPublicoOut] = None  # Make it optional
    
    model_config = {"from_attributes": True}

class EntregaDetailOut(EntregaOut):
    destinatario: Optional[dict] = None                   # ← opcional
    respuestas: List[dict] = []
