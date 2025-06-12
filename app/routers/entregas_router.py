from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user, validate_subscriber_access
from app.services.campanas_service import get_campana
from app.schemas.auth import TokenData
from app.schemas.entregas_schema import (
    EntregaCreate, EntregaUpdate, EntregaOut, EntregaDetailOut, EntregaPublicaOut
)
from app.services.entregas_service import (
    ESTADO_RESPONDIDO, create_entrega, get_entrega, get_entrega_by_destinatario, get_entrega_con_plantilla, list_entregas,
    update_entrega, delete_entrega,
    mark_as_sent, mark_as_responded
)

router = APIRouter(
    prefix="/campanas/{campana_id}/entregas",
    tags=["Entregas"]
)

public_router = APIRouter(
    prefix="/public/entregas",
    tags=["Entregas Públicas"]
)

async def validate_campana_access(
    campana_id: UUID,
    token_data: TokenData,
    db: Session
) -> bool:
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para acceder a esta campaña"
        )
    return True

@router.post("", response_model=EntregaOut)
async def create_entrega_endpoint(
    campana_id: UUID,
    payload: EntregaCreate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crea una nueva entrega"""
    await validate_campana_access(campana_id, token_data, db)
    
    entrega = await create_entrega(db, campana_id, payload)
    return entrega

@router.get("", response_model=List[EntregaOut])
async def list_entregas_endpoint(
    campana_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=1000),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_campana_access(campana_id, token_data, db)
    return list_entregas(db, campana_id, skip, limit)

@router.get("/{entrega_id}", response_model=EntregaDetailOut)
async def get_entrega_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    return entrega

@router.patch("/{entrega_id}", response_model=EntregaOut)
async def update_entrega_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    payload: EntregaUpdate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    return update_entrega(db, entrega_id, payload)

@router.delete("/{entrega_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entrega_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    delete_entrega(db, entrega_id)

# Endpoints adicionales para estados específicos
@router.post("/{entrega_id}/mark-sent", response_model=EntregaOut)
async def mark_as_sent_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    return mark_as_sent(db, entrega_id)

@router.post("/{entrega_id}/mark-responded", response_model=EntregaOut)
async def mark_as_responded_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    return mark_as_responded(db, entrega_id)

@public_router.get("/{entrega_id}/plantilla", response_model=EntregaPublicaOut)
async def get_plantilla_entrega_publica(
    entrega_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Endpoint público que devuelve la plantilla, sus preguntas y el destinatario asociados a una entrega.
    No requiere autenticación.
    """
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega or not entrega.campana or not entrega.campana.plantilla:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Entrega o plantilla no encontrada"
        )
    
    # Verificar que la entrega esté en un estado válido para ser respondida
    if entrega.estado_id == ESTADO_RESPONDIDO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta encuesta ya ha sido respondida"
        )
    
    return {
        "id": entrega.id,
        "plantilla": entrega.campana.plantilla,
        "destinatario": entrega.destinatario
    }

@public_router.get("/buscar", response_model=EntregaPublicaOut)
async def find_entrega_endpoint(
    email: str = Query(None, description="Email del destinatario"),
    telefono: str = Query(None, description="Teléfono del destinatario"),
    db: Session = Depends(get_db)
):
    """
    Busca una entrega pendiente por email o teléfono del destinatario.
    Se debe proporcionar al menos uno de los dos parámetros.
    """
    if not email and not telefono:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar email o teléfono"
        )
    
    entrega = get_entrega_by_destinatario(db, email, telefono)
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró ninguna entrega pendiente"
        )
    
    # Solo devolver si está pendiente o enviada (no respondida)
    if entrega.estado_id == ESTADO_RESPONDIDO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La encuesta ya ha sido respondida"
        )
    
    return entrega