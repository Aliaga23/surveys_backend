from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user, validate_subscriber_access
from app.core.security import require_suscriptor_activo
from app.models.cuenta_usuario import CuentaUsuario
from app.schemas.auth import TokenData
from app.schemas.plantillas_schema import (
    PlantillaCreate, PlantillaUpdate, PlantillaOut, PlantillaDetailOut
)
from app.services.plantillas_service import (
    create_plantilla, get_plantilla, get_plantilla_con_preguntas,
    list_plantillas, update_plantilla, delete_plantilla
)

router = APIRouter(
    prefix="/plantillas",
    tags=["Plantillas"]
)

@router.post("", response_model=PlantillaOut, status_code=status.HTTP_201_CREATED)
async def create_plantilla_endpoint(
    payload: PlantillaCreate,
    token_data: TokenData = Depends(require_suscriptor_activo),
    db: Session = Depends(get_db)
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para crear plantillas"
        )
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    return create_plantilla(db, payload, suscriptor_id)

@router.get("", response_model=List[PlantillaOut])
async def list_plantillas_endpoint(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para listar plantillas"
        )
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    return list_plantillas(db, suscriptor_id)

@router.get("/{plantilla_id}", response_model=PlantillaDetailOut)
async def get_plantilla_endpoint(
    plantilla_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    plantilla = get_plantilla_con_preguntas(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta plantilla"
        )
    
    return plantilla

@router.patch("/{plantilla_id}", response_model=PlantillaOut)
async def update_plantilla_endpoint(
    plantilla_id: UUID,
    payload: PlantillaUpdate,
    token_data: TokenData = Depends(require_suscriptor_activo),
    db: Session = Depends(get_db)
):
    plantilla = get_plantilla(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para modificar esta plantilla"
        )
    
    return update_plantilla(db, plantilla_id, payload)

@router.delete("/{plantilla_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plantilla_endpoint(
    plantilla_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    plantilla = get_plantilla(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para eliminar esta plantilla"
        )
    
    delete_plantilla(db, plantilla_id)