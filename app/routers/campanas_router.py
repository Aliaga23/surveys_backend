from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user, validate_subscriber_access
from app.models.cuenta_usuario import CuentaUsuario
from app.schemas.auth import TokenData
from app.schemas.campanas_schema import CampanaCreate, CampanaOut, CampanaUpdate, CampanaDetailOut, CampanaFullDetailOut
from app.services.campanas_service import (
    create_campana, get_campana, list_campanas, update_campana, delete_campana,
    get_campana_full_detail,
    ESTADO_BORRADOR, ESTADO_PROGRAMADA, ESTADO_ENVIADA, ESTADO_CERRADA
)

router = APIRouter(
    prefix="/campanas",
    tags=["Campañas"]
)

@router.post("", response_model=CampanaOut, status_code=status.HTTP_201_CREATED)
async def create_campana_endpoint(
    payload: CampanaCreate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para crear campañas"
        )
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    return create_campana(db, payload, suscriptor_id)

@router.get("", response_model=List[CampanaOut])
async def list_campanas_endpoint(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para listar campañas"
        )
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    return list_campanas(db, suscriptor_id)

@router.get("/{campana_id}", response_model=CampanaDetailOut)
async def get_campana_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta campaña"
        )
    
    return campana

@router.patch("/{campana_id}", response_model=CampanaOut)
async def update_campana_endpoint(
    campana_id: UUID,
    payload: CampanaUpdate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para modificar esta campaña"
        )
    
    return update_campana(db, campana_id, payload)

@router.delete("/{campana_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campana_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para eliminar esta campaña"
        )
    
    delete_campana(db, campana_id)

@router.get("/{campana_id}/full-detail", response_model=CampanaFullDetailOut)
async def get_campana_full_detail_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene todos los detalles de una campaña incluyendo:
    - Información de la plantilla con sus preguntas y opciones
    - Todas las entregas con sus destinatarios
    - Todas las respuestas recibidas
    - Estadísticas generales
    """
    campana = get_campana_full_detail(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta campaña"
        )
    
    return campana