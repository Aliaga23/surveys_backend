from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.entregas_service import get_entrega
from app.schemas.auth import TokenData
from app.schemas.respuestas_schema import (
    RespuestaEncuestaCreate, RespuestaEncuestaUpdate, RespuestaEncuestaOut
)
from app.services.respuestas_service import (
    create_respuesta, get_respuesta, list_respuestas_by_entrega,
    update_respuesta, delete_respuesta
)

# Router público para respuestas de encuestas
public_router = APIRouter(
    prefix="/public/entregas/{entrega_id}/respuestas",
    tags=["Respuestas Públicas"]
)

# Router privado para administración de respuestas
private_router = APIRouter(
    prefix="/campanas/{campana_id}/entregas/{entrega_id}/respuestas",
    tags=["Respuestas Admin"]
)

@public_router.post("", response_model=RespuestaEncuestaOut, status_code=status.HTTP_201_CREATED)
async def submit_respuesta(
    entrega_id: UUID,
    payload: RespuestaEncuestaCreate,
    db: Session = Depends(get_db)
):
    entrega = get_entrega(db, entrega_id)
    if not entrega:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    
    # Validar que la entrega no haya sido respondida ya
    if entrega.respondido_en:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta encuesta ya ha sido respondida"
        )
    
    return create_respuesta(db, entrega_id, payload)

@public_router.get("/{respuesta_id}", response_model=RespuestaEncuestaOut)
async def view_respuesta(
    entrega_id: UUID,
    respuesta_id: UUID,
    db: Session = Depends(get_db)
):
    respuesta = get_respuesta(db, respuesta_id)
    if not respuesta or respuesta.entrega_id != entrega_id:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    return respuesta

@private_router.post("", response_model=RespuestaEncuestaOut, status_code=status.HTTP_201_CREATED)
async def create_respuesta_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    payload: RespuestaEncuestaCreate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_entrega_access(campana_id, entrega_id, token_data, db)
    return create_respuesta(db, entrega_id, payload)

@private_router.get("", response_model=List[RespuestaEncuestaOut])
async def list_respuestas_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_entrega_access(campana_id, entrega_id, token_data, db)
    return list_respuestas_by_entrega(db, entrega_id)

@private_router.get("/{respuesta_id}", response_model=RespuestaEncuestaOut)
async def get_respuesta_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    respuesta_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_entrega_access(campana_id, entrega_id, token_data, db)
    respuesta = get_respuesta(db, respuesta_id)
    if not respuesta or respuesta.entrega_id != entrega_id:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    return respuesta

@private_router.patch("/{respuesta_id}", response_model=RespuestaEncuestaOut)
async def update_respuesta_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    respuesta_id: UUID,
    payload: RespuestaEncuestaUpdate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_entrega_access(campana_id, entrega_id, token_data, db)
    respuesta = get_respuesta(db, respuesta_id)
    if not respuesta or respuesta.entrega_id != entrega_id:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    return update_respuesta(db, respuesta_id, payload)

@private_router.delete("/{respuesta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_respuesta_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    respuesta_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_entrega_access(campana_id, entrega_id, token_data, db)
    respuesta = get_respuesta(db, respuesta_id)
    if not respuesta or respuesta.entrega_id != entrega_id:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    delete_respuesta(db, respuesta_id)