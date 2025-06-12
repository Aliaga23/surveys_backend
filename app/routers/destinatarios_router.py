from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.cuenta_usuario import CuentaUsuario
from app.schemas.auth import TokenData
from app.schemas.destinatarios_schema import (
    DestinarioCreate, DestinarioUpdate, DestinarioOut
)
from app.services.destinatarios_service import (
    create_destinatario, get_destinatario,
    list_destinatarios, update_destinatario, delete_destinatario,
    process_excel_destinatarios
)

router = APIRouter(
    prefix="/destinatarios",
    tags=["Destinatarios"]
)

@router.post("", response_model=DestinarioOut, status_code=status.HTTP_201_CREATED)
async def create_destinatario_endpoint(
    payload: DestinarioCreate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para crear destinatarios"
        )
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    return create_destinatario(db, suscriptor_id, payload)

@router.get("", response_model=List[DestinarioOut])
async def list_destinatarios_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=1000),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para listar destinatarios"
        )
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    return list_destinatarios(db, suscriptor_id, skip, limit)

@router.get("/{destinatario_id}", response_model=DestinarioOut)
async def get_destinatario_endpoint(
    destinatario_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    destinatario = get_destinatario(db, destinatario_id)
    if not destinatario:
        raise HTTPException(status_code=404, detail="Destinatario no encontrado")
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    if destinatario.suscriptor_id != suscriptor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver este destinatario"
        )
    
    return destinatario

@router.patch("/{destinatario_id}", response_model=DestinarioOut)
async def update_destinatario_endpoint(
    destinatario_id: UUID,
    payload: DestinarioUpdate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    destinatario = get_destinatario(db, destinatario_id)
    if not destinatario:
        raise HTTPException(status_code=404, detail="Destinatario no encontrado")
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    if destinatario.suscriptor_id != suscriptor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para modificar este destinatario"
        )
    
    return update_destinatario(db, destinatario_id, payload)

@router.delete("/{destinatario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_destinatario_endpoint(
    destinatario_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    destinatario = get_destinatario(db, destinatario_id)
    if not destinatario:
        raise HTTPException(status_code=404, detail="Destinatario no encontrado")
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    if destinatario.suscriptor_id != suscriptor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para eliminar este destinatario"
        )
    
    delete_destinatario(db, destinatario_id)

@router.post("/upload-excel", status_code=status.HTTP_200_OK)
async def upload_destinatarios_excel(
    file: UploadFile = File(...),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sube un archivo Excel con destinatarios.
    El Excel debe tener las columnas: nombre, email, telefono
    """
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para subir destinatarios"
        )
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    result = await process_excel_destinatarios(db, file, suscriptor_id)
    return result