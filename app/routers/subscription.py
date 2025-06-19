from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import stripe

from app.core.database import get_db
from app.core.security import get_admin_user, get_empresa_user
from app.core.config import settings

from app.services.subscription import (
    get_plan, list_planes, create_plan, update_plan, delete_plan,
    get_suscripcion, list_suscripciones, create_suscripcion,
    update_suscripcion, delete_suscripcion
)
from app.schemas.subscription import (
    PlanSuscripcionCreate, PlanSuscripcionOut, PlanSuscripcionUpdate,
    SuscripcionSuscriptorCreate, SuscripcionSuscriptorOut, SuscripcionSuscriptorUpdate
)
from app.models.subscription import SuscripcionSuscriptor
from app.models.suscriptor import Suscriptor


# Configuración del router
router = APIRouter(
    prefix="/subscription",
    tags=["Suscripciones"]
)

# ---------------- PLANES DE SUSCRIPCIÓN ----------------

@router.post(
    "/planes",
    response_model=PlanSuscripcionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_admin_user)]
)
def create_plan_endpoint(
    payload: PlanSuscripcionCreate,
    db: Session = Depends(get_db)
):
    return create_plan(db, payload)

@router.get(
    "/planes",
    response_model=list[PlanSuscripcionOut]
)
def list_planes_endpoint(
    db: Session = Depends(get_db)
):
    return list_planes(db)

@router.get(
    "/planes/{plan_id}",
    response_model=PlanSuscripcionOut
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
    dependencies=[Depends(get_admin_user)]
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
    dependencies=[Depends(get_admin_user)]
)
def delete_plan_endpoint(
    plan_id: int,
    db: Session = Depends(get_db)
):
    delete_plan(db, plan_id)


# ---------------- SUSCRIPCIONES DE SUSCRIPTOR ----------------

@router.post(
    "/suscripciones",
    response_model=SuscripcionSuscriptorOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_empresa_user)]
)
def create_suscripcion_endpoint(
    payload: SuscripcionSuscriptorCreate,
    db: Session = Depends(get_db)
):
    return create_suscripcion(db, payload)

@router.get(
    "/suscripciones",
    response_model=list[SuscripcionSuscriptorOut],
    dependencies=[Depends(get_empresa_user)]
)
def list_suscripciones_endpoint(
    suscriptor_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return list_suscripciones(db, suscriptor_id)

@router.get(
    "/suscripciones/{sus_id}",
    response_model=SuscripcionSuscriptorOut,
    dependencies=[Depends(get_empresa_user)]
)
def get_suscripcion_endpoint(
    sus_id: str,
    db: Session = Depends(get_db)
):
    sus = get_suscripcion(db, sus_id)
    if not sus:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    return sus

@router.put(
    "/suscripciones/{sus_id}",
    response_model=SuscripcionSuscriptorOut,
    dependencies=[Depends(get_empresa_user)]
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
    dependencies=[Depends(get_empresa_user)]
)
def delete_suscripcion_endpoint(
    sus_id: str,
    db: Session = Depends(get_db)
):
    delete_suscripcion(db, sus_id)


# ---------------- STRIPE SUSCRIPCIÓN ----------------

@router.post(
    "/stripe-suscripcion",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_empresa_user)]
)
def iniciar_suscripcion_stripe(
    suscriptor_id: str,
    plan_id: int,
    db: Session = Depends(get_db)
):
    from app.services.stripe_service import crear_suscripcion_stripe
    return crear_suscripcion_stripe(db, suscriptor_id, plan_id)


# ---------------- STRIPE WEBHOOK ----------------

@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail="Webhook error")

    print(f"Evento recibido: {event['type']}")

    try:
        if event["type"] == "invoice.paid":
            stripe_sub_id = event["data"]["object"]["subscription"]
            suscripcion = db.query(SuscripcionSuscriptor).filter_by(stripe_subscription_id=stripe_sub_id).first()
            if suscripcion:
                suscripcion.estado = "activo"
                suscriptor = db.query(Suscriptor).filter_by(id=suscripcion.suscriptor_id).first()
                suscriptor.estado = "activo"
                db.commit()

        elif event["type"] == "customer.subscription.deleted":
            stripe_sub_id = event["data"]["object"]["id"]
            suscripcion = db.query(SuscripcionSuscriptor).filter_by(stripe_subscription_id=stripe_sub_id).first()
            if suscripcion:
                suscripcion.estado = "inactivo"
                suscriptor = db.query(Suscriptor).filter_by(id=suscripcion.suscriptor_id).first()
                suscriptor.estado = "inactivo"
                db.commit()

    except Exception as e:
        print(f"Error procesando evento: {e}")
        raise HTTPException(status_code=500, detail="Error procesando evento")

    return {"status": "success"}
