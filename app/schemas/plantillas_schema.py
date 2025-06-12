from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel

class PlantillaBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    activo: Optional[bool] = True

class PlantillaCreate(PlantillaBase):
    pass

class PlantillaUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    activo: Optional[bool] = None

class PreguntaInPlantilla(BaseModel):
    id: UUID
    orden: int
    texto: str
    tipo_pregunta_id: int
    obligatorio: bool
    opciones: Optional[List[dict]] = None

    model_config = {"from_attributes": True}

class PlantillaOut(PlantillaBase):
    id: UUID
    suscriptor_id: UUID
    creado_en: datetime

    model_config = {"from_attributes": True}

class PlantillaDetailOut(PlantillaOut):
    preguntas: List[PreguntaInPlantilla]