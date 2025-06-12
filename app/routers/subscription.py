from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, get_admin_user, get_empresa_user

from app.services.subscription import (
    get_plan, list_planes, create_plan, update_plan, delete_plan,
    get_suscripcion, list_suscripciones, create_suscripcion,
    update_suscripcion, delete_suscripcion
)
from app.schemas.subscription import (
    PlanSuscripcionCreate, PlanSuscripcionOut, PlanSuscripcionUpdate,
    SuscripcionSuscriptorCreate, SuscripcionSuscriptorOut, SuscripcionSuscriptorUpdate
)

# Ya no usamos dependencies a nivel de router, sino a nivel de endpoint
router = APIRouter(
    prefix="/subscription",
    tags=["Suscripciones"]
)

# Ã¢â‚¬â€Ã¢â‚¬â€ Planes de SuscripciÃƒÂ³n (solo admin) Ã¢â‚¬â€__
@router.post(
    "/planes",
    response_model=PlanSuscripcionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_admin_user)]  # Solo admin puede crear planes
)
def create_plan_endpoint(
    payload: PlanSuscripcionCreate,
    db: Session = Depends(get_db)
):
    return create_plan(db, payload)

@router.get(
    "/planes",
    response_model=list[PlanSuscripcionOut]
    # No tiene restricciones, cualquiera puede ver los planes
)
def list_planes_endpoint(
    db: Session = Depends(get_db)
):
    return list_planes(db)

@router.get(
    "/planes/{plan_id}",
    response_model=PlanSuscripcionOut
    # No tiene restricciones, cualquiera puede ver un plan especÃƒÂ­fico
)
def get_plan_endpoint(
    plan_id: int,
    db: Session = Depends(get_db)
):
    plan = get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    return plan

@router.put(
    "/planes/{plan_id}",
    response_model=PlanSuscripcionOut,
    dependencies=[Depends(get_admin_user)]  # Solo admin puede actualizar planes
)
def update_plan_endpoint(
    plan_id: int,
    payload: PlanSuscripcionUpdate,
    db: Session = Depends(get_db)
):
    return update_plan(db, plan_id, payload)

@router.delete(
    "/planes/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_admin_user)]  # Solo admin puede eliminar planes
)
def delete_plan_endpoint(
    plan_id: int,
    db: Session = Depends(get_db)
):
    delete_plan(db, plan_id)


# Ã¢â‚¬â€Ã¢â‚¬â€ Suscripciones de Suscriptor (solo empresa) Ã¢â‚¬â€__
@router.post(
    "/suscripciones",
    response_model=SuscripcionSuscriptorOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_empresa_user)]  # Solo empresa puede crear suscripciones
)
def create_suscripcion_endpoint(
    payload: SuscripcionSuscriptorCreate,
    db: Session = Depends(get_db)
):
    return create_suscripcion(db, payload)

@router.get(
    "/suscripciones",
    response_model=list[SuscripcionSuscriptorOut],
    dependencies=[Depends(get_empresa_user)]  # Solo empresa puede listar suscripciones
)
def list_suscripciones_endpoint(
    suscriptor_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return list_suscripciones(db, suscriptor_id)

@router.get(
    "/suscripciones/{sus_id}",
    response_model=SuscripcionSuscriptorOut,
    dependencies=[Depends(get_empresa_user)]  # Solo empresa puede ver una suscripciÃƒÂ³n especÃƒÂ­fica
)
def get_suscripcion_endpoint(
    sus_id: str,
    db: Session = Depends(get_db)
):
    sus = get_suscripcion(db, sus_id)
    if not sus:
        raise HTTPException(status_code=404, detail="SuscripciÃƒÂ³n no encontrada")
    return sus

@router.put(
    "/suscripciones/{sus_id}",
    response_model=SuscripcionSuscriptorOut,
    dependencies=[Depends(get_empresa_user)]  # Solo empresa puede actualizar suscripciones
)
def update_suscripcion_endpoint(
    sus_id: str,
    payload: SuscripcionSuscriptorUpdate,
    db: Session = Depends(get_db)
):
    return update_suscripcion(db, sus_id, payload)

@router.delete(
    "/suscripciones/{sus_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_empresa_user)]  # Solo empresa puede eliminar suscripciones
)
def delete_suscripcion_endpoint(
    sus_id: str,
    db: Session = Depends(get_db)
):
    delete_suscripcion(db, sus_id)
