# app/core/security.py

import os
from datetime import datetime, timedelta

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from uuid import UUID
from dotenv import load_dotenv

from app.core.database import get_db
from app.schemas.auth import TokenData
from app.models.cuenta_usuario import CuentaUsuario
from app.models.suscriptor import Suscriptor

# 1) Carga variables de entorno
load_dotenv()

# 2) Lee SECRET_KEY y valida
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY or not isinstance(SECRET_KEY, str):
    raise RuntimeError("Debes definir SECRET_KEY en tu .env como un string")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(subject: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "role": role, "exp": expire}
    # SECRET_KEY ya está garantizado como str
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> TokenData:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        role_name: str = payload.get("role")
        if user_id is None or role_name is None:
            raise credentials_exception
        return TokenData(sub=user_id, role=role_name)
    except JWTError:
        raise credentials_exception

def get_admin_user(token_data: TokenData = Depends(get_current_user)) -> TokenData:
    """Verifica que el usuario sea un administrador"""
    if token_data.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Se requiere rol de administrador"
        )
    return token_data

def get_empresa_user(token_data: TokenData = Depends(get_current_user)) -> TokenData:
    """Verifica que el usuario tenga rol de empresa"""
    if token_data.role != "empresa":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Se requiere rol de empresa"
        )
    return token_data

async def validate_subscriber_access(
    token_data: TokenData,
    suscriptor_id: UUID,
    db: Session = Depends(get_db)
) -> bool:
    """Valida que el usuario tenga acceso a los recursos del suscriptor"""
    if token_data.role == "empresa" and token_data.sub == str(suscriptor_id):
        return True
    elif token_data.role == "operator":
        user = db.query(CuentaUsuario).filter(CuentaUsuario.id == UUID(token_data.sub)).first()
        if user and user.suscriptor_id == suscriptor_id:
            return True
    return False


def require_suscriptor_activo(
    token_data: TokenData = Depends(get_empresa_user),
    db: Session = Depends(get_db)
) -> TokenData:
    """Verifica que el suscriptor esté activo además de tener rol empresa"""
    suscriptor = db.query(Suscriptor).filter_by(id=token_data.sub).first()
    if not suscriptor or suscriptor.estado != "activo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu suscripción no está activa o fue cancelada."
        )
    return token_data