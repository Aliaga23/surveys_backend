from typing import Optional
from pydantic import BaseModel

class RolBase(BaseModel):
    nombre: str

class RolCreate(RolBase):
    pass

class RolUpdate(BaseModel):
    nombre: Optional[str] = None

class RolOut(RolBase):
    id: int
    model_config = {"from_attributes": True}


class TipoPreguntaBase(BaseModel):
    nombre: str

class TipoPreguntaCreate(TipoPreguntaBase):
    pass

class TipoPreguntaUpdate(BaseModel):
    nombre: Optional[str] = None

class TipoPreguntaOut(TipoPreguntaBase):
    id: int
    model_config = {"from_attributes": True}


class CanalBase(BaseModel):
    nombre: str

class CanalCreate(CanalBase):
    pass

class CanalUpdate(BaseModel):
    nombre: Optional[str] = None

class CanalOut(CanalBase):
    id: int
    model_config = {"from_attributes": True}


class EstadoCampanaBase(BaseModel):
    nombre: str

class EstadoCampanaCreate(EstadoCampanaBase):
    pass

class EstadoCampanaUpdate(BaseModel):
    nombre: Optional[str] = None

class EstadoCampanaOut(EstadoCampanaBase):
    id: int
    model_config = {"from_attributes": True}


class EstadoEntregaBase(BaseModel):
    nombre: str

class EstadoEntregaCreate(EstadoEntregaBase):
    pass

class EstadoEntregaUpdate(BaseModel):
    nombre: Optional[str] = None

class EstadoEntregaOut(EstadoEntregaBase):
    id: int
    model_config = {"from_attributes": True}


class EstadoDocumentoBase(BaseModel):
    nombre: str

class EstadoDocumentoCreate(EstadoDocumentoBase):
    pass

class EstadoDocumentoUpdate(BaseModel):
    nombre: Optional[str] = None

class EstadoDocumentoOut(EstadoDocumentoBase):
    id: int
    model_config = {"from_attributes": True}


class EstadoPagoBase(BaseModel):
    nombre: str

class EstadoPagoCreate(EstadoPagoBase):
    pass

class EstadoPagoUpdate(BaseModel):
    nombre: Optional[str] = None

class EstadoPagoOut(EstadoPagoBase):
    id: int
    model_config = {"from_attributes": True}


class MetodoPagoBase(BaseModel):
    nombre: str

class MetodoPagoCreate(MetodoPagoBase):
    pass

class MetodoPagoUpdate(BaseModel):
    nombre: Optional[str] = None

class MetodoPagoOut(MetodoPagoBase):
    id: int
    model_config = {"from_attributes": True}
