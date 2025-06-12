from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field

class OpcionBase(BaseModel):
    texto: str
    valor: Optional[str] = None

class OpcionCreate(OpcionBase):
    pass

class OpcionOut(OpcionBase):
    id: UUID
    pregunta_id: UUID
    
    model_config = {"from_attributes": True}

class PreguntaBase(BaseModel):
    orden: int
    texto: str
    tipo_pregunta_id: int
    obligatorio: bool = True

class PreguntaCreate(PreguntaBase):
    pass

class PreguntaUpdate(BaseModel):
    orden: Optional[int] = None
    texto: Optional[str] = None
    tipo_pregunta_id: Optional[int] = None
    obligatorio: Optional[bool] = None

class PreguntaOut(PreguntaBase):
    id: UUID
    plantilla_id: UUID
    opciones: List[OpcionOut] = []

    model_config = {"from_attributes": True}