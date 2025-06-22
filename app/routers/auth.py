# app/routers/auth.py

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_user
from app.core.config import settings

from app.models.catalogos import Rol
from app.models.administrador import Administrador
from app.models.suscriptor import Suscriptor
from app.models.cuenta_usuario import CuentaUsuario

from app.schemas.auth import (
    AdminCreate, AdminOut, AdminProfileOut, ForgotPasswordRequest, LoginRequest, OperatorProfileOut, ResetPasswordRequest,
    SuscriptorCreate, SuscriptorOut,
    CuentaUsuarioCreate, CuentaUsuarioOut, SuscriptorProfileOut,
    Token, UserProfileOut, TokenData
)

from uuid import UUID

from app.services.email_service import enviar_email_recuperacion_contrasena, enviar_email_verificacion
import secrets, jwt

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
    if not user:
        user = db.query(Suscriptor).filter_by(email=email).first()
    if not user:
        user = db.query(CuentaUsuario).filter_by(email=email).first()

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


@router.post(
    "/request-registration",
    status_code=status.HTTP_200_OK
)
async def request_registration(
    payload: SuscriptorCreate,
    db: Session = Depends(get_db)
):
    # 1. Verifica que el email no esté registrado
    if db.query(Suscriptor).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    # 2. Verifica que no haya un admin o cuenta_usuario con ese email (por seguridad)
    if db.query(Administrador).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    if db.query(CuentaUsuario).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    # 3. Generar el token (JWT) con datos del registro
    from app.core.security import hash_password
    from app.core.security import create_access_token
    from datetime import timedelta

    password_hash = hash_password(payload.password)

    # Creamos un payload simple
    from datetime import datetime, timezone
    import jwt

    token_data = {
        "sub": payload.email,
        "nombre": payload.nombre,
        "telefono": payload.telefono,
        "password_hash": password_hash,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }

    token = jwt.encode(
        token_data,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    # 4. Armar el link
    url_verificacion = f"{settings.FRONTEND_URL}/verify-registration?token={token}"

    # 5. Enviar el email
    from app.services.email_service import enviar_email_verificacion
    enviado = await enviar_email_verificacion(
        destinatario_email=payload.email,
        destinatario_nombre=payload.nombre,
        url_verificacion=url_verificacion
    )

    if not enviado:
        raise HTTPException(status_code=500, detail="No se pudo enviar el correo de verificación")

    return {"message": "Correo de verificación enviado. Revisa tu bandeja de entrada."}



@router.get("/verify-registration")
def verify_registration(
    token: str,
    db: Session = Depends(get_db)
):
    import jwt
    from jwt import ExpiredSignatureError, InvalidTokenError
    from uuid import uuid4
    from app.core.security import create_access_token

    try:
        # Decodificar el token
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        email = payload["sub"]
        nombre = payload["nombre"]
        telefono = payload["telefono"]
        password_hash = payload["password_hash"]

        # Verificar que el email no esté registrado
        if db.query(Suscriptor).filter_by(email=email).first():
            raise HTTPException(status_code=400, detail="El email ya está registrado")
        if db.query(Administrador).filter_by(email=email).first():
            raise HTTPException(status_code=400, detail="El email ya está registrado")
        if db.query(CuentaUsuario).filter_by(email=email).first():
            raise HTTPException(status_code=400, detail="El email ya está registrado")

        # Buscar el rol de empresa
        rol_empresa = db.query(Rol).filter_by(nombre="empresa").first()
        if not rol_empresa:
            raise HTTPException(status_code=500, detail="Rol 'empresa' no configurado")

        # Crear el suscriptor
        sus = Suscriptor(
            id=uuid4(),
            nombre=nombre,
            email=email,
            telefono=telefono,
            password_hash=password_hash,
            rol_id=rol_empresa.id,
            estado="inactivo"
        )
        db.add(sus)
        db.commit()
        db.refresh(sus)

        # Generar access_token
        access_token = create_access_token(subject=str(sus.id), role=rol_empresa.nombre)

        return {
            "message": "Cuenta activada correctamente",
            "access_token": access_token
        }

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="El enlace ha expirado")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al activar la cuenta: {str(e)}")


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    email = payload.email

    user = (
        db.query(Administrador).filter_by(email=email).first()
        or db.query(Suscriptor).filter_by(email=email).first()
        or db.query(CuentaUsuario).filter_by(email=email).first()
    )
    if not user:
        return {"message": "Si el correo está registrado, se enviará un enlace para restablecer la contraseña."}

    reset_token = secrets.token_urlsafe(32)
    token_data = {
        "sub": email,
        "reset_token": reset_token,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    enviado = await enviar_email_recuperacion_contrasena(
        destinatario_email=email,
        destinatario_nombre=getattr(user, "nombre", getattr(user, "nombre_completo", "")),
        url_reset=reset_link
    )

    if not enviado:
        raise HTTPException(status_code=500, detail="No se pudo enviar el correo de recuperación")

    return {"message": "Correo enviado correctamente"}

@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    try:
        decoded = jwt.decode(payload.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = decoded["sub"]

        user = (
            db.query(Administrador).filter_by(email=email).first()
            or db.query(Suscriptor).filter_by(email=email).first()
            or db.query(CuentaUsuario).filter_by(email=email).first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        user.password_hash = hash_password(payload.new_password)
        db.commit()

        return {"message": "Contraseña actualizada correctamente"}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="El token ha expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Token inválido")
