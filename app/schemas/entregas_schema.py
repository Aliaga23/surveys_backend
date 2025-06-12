from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel

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
    nombre: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    
    model_config = {"from_attributes": True}

class EntregaPublicaOut(BaseModel):
    id: UUID
    plantilla: PlantillaPublicaOut
    destinatario: DestinatarioPublicoOut
    
    model_config = {"from_attributes": True}

class EntregaBase(BaseModel):
    destinatario_id: UUID
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

    model_config = {"from_attributes": True}

class EntregaDetailOut(EntregaOut):
    destinatario: dict
    respuestas: List[dict] = []