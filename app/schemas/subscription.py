from pydantic import BaseModel, condecimal
from datetime import datetime
from uuid import UUID
from typing import Optional, List

class PlanSuscripcionBase(BaseModel):
    nombre: str
    precio_mensual: condecimal(max_digits=10, decimal_places=2)
    descripcion: Optional[str] = None

class PlanSuscripcionCreate(PlanSuscripcionBase):
    pass

class PlanSuscripcionUpdate(BaseModel):
    nombre: Optional[str]
    precio_mensual: Optional[condecimal(max_digits=10, decimal_places=2)]
    descripcion: Optional[str]

class PlanSuscripcionOut(PlanSuscripcionBase):
    id: int
    creado_en: datetime

    model_config = {"from_attributes": True}


class SuscripcionSuscriptorBase(BaseModel):
    suscriptor_id: UUID
    plan_id: int
    inicia_en: datetime
    expira_en: Optional[datetime] = None
    estado: Optional[str] = "activo"

class SuscripcionSuscriptorCreate(SuscripcionSuscriptorBase):
    pass

class SuscripcionSuscriptorUpdate(BaseModel):
    expira_en: Optional[datetime]
    estado: Optional[str]

class SuscripcionSuscriptorOut(SuscripcionSuscriptorBase):
    id: UUID

    model_config = {"from_attributes": True}


# Para endpoints que devuelven listas
class PlanesList(BaseModel):
    planes: List[PlanSuscripcionOut]

class SuscripcionesList(BaseModel):
    suscripciones: List[SuscripcionSuscriptorOut]
