# app/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_user

from app.models.catalogos import Rol
from app.models.administrador import Administrador
from app.models.suscriptor import Suscriptor
from app.models.cuenta_usuario import CuentaUsuario

from app.schemas.auth import (
    AdminCreate, AdminOut, AdminProfileOut, LoginRequest, OperatorProfileOut,
    SuscriptorCreate, SuscriptorOut,
    CuentaUsuarioCreate, CuentaUsuarioOut, SuscriptorProfileOut,
    Token, UserProfileOut, TokenData
)

from uuid import UUID

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register/administrador",
    response_model=AdminOut,
    status_code=status.HTTP_201_CREATED
)
def register_admin(
    payload: AdminCreate,
    db: Session = Depends(get_db)
):
    if db.query(Administrador).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya estÃƒÂ¡ registrado")
    rol_admin = db.query(Rol).filter_by(nombre="admin").first()
    if not rol_admin:
        raise HTTPException(status_code=500, detail="Rol 'admin' no configurado")
    hashed = hash_password(payload.password)
    admin = Administrador(
        email=payload.email,
        password_hash=hashed,
        rol_id=rol_admin.id
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@router.post(
    "/register/suscriptor",
    response_model=SuscriptorOut,
    status_code=status.HTTP_201_CREATED
)
def register_suscriptor(
    payload: SuscriptorCreate,
    db: Session = Depends(get_db)
):
    if db.query(Suscriptor).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya estÃƒÂ¡ registrado")
    rol_empresa = db.query(Rol).filter_by(nombre="empresa").first()
    if not rol_empresa:
        raise HTTPException(status_code=500, detail="Rol 'empresa' no configurado")
    hashed = hash_password(payload.password)
    sus = Suscriptor(
        nombre=payload.nombre,
        email=payload.email,
        telefono=payload.telefono,
        password_hash=hashed,
        rol_id=rol_empresa.id
    )
    db.add(sus)
    db.commit()
    db.refresh(sus)
    return sus


@router.post(
    "/register/usuario",
    response_model=CuentaUsuarioOut,
    status_code=status.HTTP_201_CREATED
)
def register_usuario(
    payload: CuentaUsuarioCreate,
    db: Session = Depends(get_db)
):
    exists = db.query(CuentaUsuario).filter_by(
        suscriptor_id=payload.suscriptor_id,
        email=payload.email
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="El email ya estÃƒÂ¡ registrado para este suscriptor")
    rol_operator = db.query(Rol).filter_by(nombre="operator").first()
    if not rol_operator:
        raise HTTPException(status_code=500, detail="Rol 'operator' no configurado")
    hashed = hash_password(payload.password)
    user = CuentaUsuario(
        suscriptor_id=payload.suscriptor_id,
        nombre_completo=payload.nombre_completo,
        email=payload.email,
        password_hash=hashed,
        rol_id=rol_operator.id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db)
):
    email = credentials.email
    password = credentials.password

    user = db.query(Administrador).filter_by(email=email).first()
    # si no existe, pruebo Suscriptor
    if not user:
        user = db.query(Suscriptor).filter_by(email=email).first()
    # si aÃƒÂºn no existe, pruebo CuentaUsuario
    if not user:
        user = db.query(CuentaUsuario).filter_by(email=email).first()

    # validaciÃƒÂ³n de credenciales
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invÃƒÂ¡lidas"
        )

    # obtengo el nombre del rol para el token
    rol = db.get(Rol, user.rol_id)
    token = create_access_token(subject=str(user.id), role=rol.nombre)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserProfileOut)
def get_current_user_profile(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Obtener el ID del usuario desde el token
    user_id = token_data.sub
    role = token_data.role
    
    if role == "admin":
        user = db.query(Administrador).filter(Administrador.id == UUID(user_id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Administrador no encontrado")
        # Obtener el objeto rol
        rol = db.get(Rol, user.rol_id)
        return AdminProfileOut(
            id=user.id,
            email=user.email,
            rol=rol.nombre,
            activo=user.activo,
            creado_en=user.creado_en
        )
        
    elif role == "empresa":
        user = db.query(Suscriptor).filter(Suscriptor.id == UUID(user_id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Suscriptor no encontrado")
        rol = db.get(Rol, user.rol_id)
        return SuscriptorProfileOut(
            id=user.id,
            email=user.email,
            rol=rol.nombre,
            nombre=user.nombre,
            telefono=user.telefono,
            estado=user.estado,
            creado_en=user.creado_en
        )
        
    elif role == "operator":
        user = db.query(CuentaUsuario).filter(CuentaUsuario.id == UUID(user_id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        rol = db.get(Rol, user.rol_id)
        return OperatorProfileOut(
            id=user.id,
            email=user.email,
            rol=rol.nombre,
            nombre_completo=user.nombre_completo,
            suscriptor_id=user.suscriptor_id,
            activo=user.activo,
            creado_en=user.creado_en
        )
    
    raise HTTPException(status_code=400, detail="Tipo de usuario no reconocido")
