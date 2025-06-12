from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, constr

class DestinarioBase(BaseModel):
    nombre: str
    telefono: Optional[constr(max_length=20)] = None
    email: Optional[EmailStr] = None

class DestinarioCreate(DestinarioBase):
    pass

class DestinarioUpdate(BaseModel):
    nombre: Optional[str] = None
    telefono: Optional[constr(max_length=20)] = None
    email: Optional[EmailStr] = None

class DestinarioOut(DestinarioBase):
    id: UUID
    suscriptor_id: UUID
    creado_en: datetime

    model_config = {"from_attributes": True}