from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user, validate_subscriber_access
from app.core.security import require_suscriptor_activo
from app.services.plantillas_service import get_plantilla
from app.schemas.auth import TokenData
from app.schemas.preguntas_schema import (
    PreguntaCreate, PreguntaUpdate, PreguntaOut
)
from app.services.preguntas_service import (
    create_pregunta, get_pregunta, list_preguntas,
    update_pregunta, delete_pregunta
)

router = APIRouter(
    prefix="/plantillas/{plantilla_id}/preguntas",
    tags=["Preguntas"]
)

async def validate_plantilla_access(
    plantilla_id: UUID,
    token_data: TokenData,
    db: Session
) -> bool:
    plantilla = get_plantilla(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para acceder a esta plantilla"
        )
    return True

@router.post("", response_model=PreguntaOut, status_code=status.HTTP_201_CREATED)
async def create_pregunta_endpoint(
    plantilla_id: UUID,
    payload: PreguntaCreate,
    token_data: TokenData = Depends(require_suscriptor_activo),
    db: Session = Depends(get_db)
):
    await validate_plantilla_access(plantilla_id, token_data, db)
    return create_pregunta(db, plantilla_id, payload)

@router.get("", response_model=List[PreguntaOut])
async def list_preguntas_endpoint(
    plantilla_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_plantilla_access(plantilla_id, token_data, db)
    return list_preguntas(db, plantilla_id)

@router.get("/{pregunta_id}", response_model=PreguntaOut)
async def get_pregunta_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_plantilla_access(plantilla_id, token_data, db)
    pregunta = get_pregunta(db, pregunta_id)
    if not pregunta or pregunta.plantilla_id != plantilla_id:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")
    return pregunta

@router.patch("/{pregunta_id}", response_model=PreguntaOut)
async def update_pregunta_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    payload: PreguntaUpdate,
    token_data: TokenData = Depends(require_suscriptor_activo),
    db: Session = Depends(get_db)
):
    await validate_plantilla_access(plantilla_id, token_data, db)
    pregunta = get_pregunta(db, pregunta_id)
    if not pregunta or pregunta.plantilla_id != plantilla_id:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")
    return update_pregunta(db, pregunta_id, payload)

@router.delete("/{pregunta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pregunta_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_plantilla_access(plantilla_id, token_data, db)
    pregunta = get_pregunta(db, pregunta_id)
    if not pregunta or pregunta.plantilla_id != plantilla_id:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")
    delete_pregunta(db, pregunta_id)