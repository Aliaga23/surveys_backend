from pydantic import BaseModel, EmailStr
from typing import Optional, Union
from datetime import datetime
from uuid import UUID

class AdminCreate(BaseModel):
    email: EmailStr
    password: str

class AdminOut(BaseModel):
    id: UUID
    email: EmailStr
    activo: bool
    rol_id: int
    creado_en: datetime
    model_config = {"from_attributes": True}


class SuscriptorCreate(BaseModel):
    nombre: str
    email: EmailStr
    telefono: Optional[str] = None
    password: str

class SuscriptorOut(BaseModel):
    id: UUID
    nombre: str
    email: EmailStr
    telefono: Optional[str]
    estado: str
    creado_en: datetime
    model_config = {"from_attributes": True}


class CuentaUsuarioCreate(BaseModel):
    suscriptor_id: UUID
    nombre_completo: str
    email: EmailStr
    password: str

class CuentaUsuarioOut(BaseModel):
    id: UUID
    suscriptor_id: UUID
    nombre_completo: str
    email: EmailStr
    activo: bool
    rol_id: int
    creado_en: datetime
    model_config = {"from_attributes": True}


# Ã¢â‚¬â€Ã¢â‚¬â€Ã¢â‚¬â€ LOGIN / TOKEN Ã¢â‚¬â€Ã¢â‚¬â€Ã¢â‚¬â€
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    sub: Optional[str]
    role: Optional[str]


# Ã¢â‚¬â€Ã¢â‚¬â€Ã¢â‚¬â€ LOGIN Ã¢â‚¬â€Ã¢â‚¬â€Ã¢â‚¬â€
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Ã¢â‚¬â€Ã¢â‚¬â€Ã¢â‚¬â€ PERFIL USUARIO Ã¢â‚¬â€Ã¢â‚¬â€Ã¢â‚¬â€
class UserProfileBase(BaseModel):
    id: UUID
    email: str
    rol: str
    creado_en: datetime
    
    model_config = {"from_attributes": True}

# Perfil especÃƒÂ­fico para administradores
class AdminProfileOut(UserProfileBase):
    tipo: str = "admin"
    activo: bool

# Perfil especÃƒÂ­fico para suscriptores
class SuscriptorProfileOut(UserProfileBase):
    tipo: str = "suscriptor"
    nombre: str
    telefono: str
    estado: Optional[str] = None

# Perfil especÃƒÂ­fico para usuarios operadores
class OperatorProfileOut(UserProfileBase):
    tipo: str = "usuario"
    nombre_completo: str
    suscriptor_id: UUID
    activo: bool

# Tipo uniÃƒÂ³n para el endpoint /me
UserProfileOut = Union[AdminProfileOut, SuscriptorProfileOut, OperatorProfileOut]