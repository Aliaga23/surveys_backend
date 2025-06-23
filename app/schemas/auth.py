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


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    sub: Optional[str]
    role: Optional[str]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserProfileBase(BaseModel):
    id: UUID
    email: str
    rol: str
    creado_en: datetime
    
    model_config = {"from_attributes": True}

class AdminProfileOut(UserProfileBase):
    tipo: str = "admin"
    activo: bool

class SuscriptorProfileOut(UserProfileBase):
    tipo: str = "suscriptor"
    nombre: str
    telefono: str
    estado: Optional[str] = None

class OperatorProfileOut(UserProfileBase):
    tipo: str = "usuario"
    nombre_completo: str
    suscriptor_id: UUID
    activo: bool

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class AdminUpdateRequest(BaseModel):
    email: EmailStr

class SuscriptorUpdateRequest(BaseModel):
    nombre: str
    email: EmailStr
    telefono: Optional[str] = None
    
UserProfileOut = Union[AdminProfileOut, SuscriptorProfileOut, OperatorProfileOut]