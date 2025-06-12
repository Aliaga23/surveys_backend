from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.auth import TokenData
from app.schemas.preguntas_schema import OpcionCreate, OpcionOut
from app.services.preguntas_service import get_pregunta
from app.services.opciones_service import (
    create_opcion, get_opcion, list_opciones,
    update_opcion, delete_opcion
)
from app.routers.preguntas_router import validate_plantilla_access

router = APIRouter(
    prefix="/plantillas/{plantilla_id}/preguntas/{pregunta_id}/opciones",
    tags=["Opciones"]
)

async def validate_pregunta_access(
    plantilla_id: UUID,
    pregunta_id: UUID,
    token_data: TokenData,
    db: Session
) -> bool:
    # Primero validamos acceso a la plantilla
    await validate_plantilla_access(plantilla_id, token_data, db)
    
    # Luego verificamos que la pregunta exista y pertenezca a la plantilla
    pregunta = get_pregunta(db, pregunta_id)
    if not pregunta or pregunta.plantilla_id != plantilla_id:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")
    return True

@router.post("", response_model=OpcionOut, status_code=status.HTTP_201_CREATED)
async def create_opcion_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    payload: OpcionCreate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_pregunta_access(plantilla_id, pregunta_id, token_data, db)
    return create_opcion(db, pregunta_id, payload)

@router.get("", response_model=List[OpcionOut])
async def list_opciones_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_pregunta_access(plantilla_id, pregunta_id, token_data, db)
    return list_opciones(db, pregunta_id)

@router.get("/{opcion_id}", response_model=OpcionOut)
async def get_opcion_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    opcion_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_pregunta_access(plantilla_id, pregunta_id, token_data, db)
    opcion = get_opcion(db, opcion_id)
    if not opcion or opcion.pregunta_id != pregunta_id:
        raise HTTPException(status_code=404, detail="Opción no encontrada")
    return opcion

@router.patch("/{opcion_id}", response_model=OpcionOut)
async def update_opcion_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    opcion_id: UUID,
    payload: OpcionCreate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_pregunta_access(plantilla_id, pregunta_id, token_data, db)
    opcion = get_opcion(db, opcion_id)
    if not opcion or opcion.pregunta_id != pregunta_id:
        raise HTTPException(status_code=404, detail="Opción no encontrada")
    return update_opcion(db, opcion_id, payload)

@router.delete("/{opcion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opcion_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    opcion_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    await validate_pregunta_access(plantilla_id, pregunta_id, token_data, db)
    opcion = get_opcion(db, opcion_id)
    if not opcion or opcion.pregunta_id != pregunta_id:
        raise HTTPException(status_code=404, detail="Opción no encontrada")
    delete_opcion(db, opcion_id)