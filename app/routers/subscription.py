from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import stripe

from app.core.database import get_db
from app.core.security import get_admin_user, get_empresa_user
from app.core.config import settings
from datetime import datetime

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
from app.models.subscription import PlanSuscripcion


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

@router.post("/stripe-checkout")
def crear_checkout_session(suscriptor_id: str, plan_id: int, db: Session = Depends(get_db)):
    suscriptor = db.query(Suscriptor).filter_by(id=suscriptor_id).first()
    plan = db.query(PlanSuscripcion).filter_by(id=plan_id).first()
    if not suscriptor or not plan:
        raise HTTPException(status_code=404, detail="Suscriptor o plan no encontrado")

    if not suscriptor.stripe_customer_id:
        customer = stripe.Customer.create(
            email=suscriptor.email,
            name=suscriptor.nombre
        )
        suscriptor.stripe_customer_id = customer.id
        db.commit()

    checkout_session = stripe.checkout.Session.create(
        customer=suscriptor.stripe_customer_id,
        line_items=[{
            'price': plan.stripe_price_id,
            'quantity': 1,
        }],
        mode='subscription',
        success_url='https://example.com/success?session_id={CHECKOUT_SESSION_ID}',
        cancel_url='https://example.com/cancel',
    )

    # Registrar en la base de datos
    nueva_suscripcion = SuscripcionSuscriptor(
        suscriptor_id=suscriptor.id,
        plan_id=plan.id,
        inicia_en=datetime.utcnow(),
        estado="pendiente",
        stripe_subscription_id=None  # aún no lo tenemos, llegará con el webhook
    )
    db.add(nueva_suscripcion)
    db.commit()

    return {"checkout_url": checkout_session.url}


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
        obj = event["data"]["object"]
        event_type = event["type"]

        if event_type == "checkout.session.completed":
            print(f"Payload completo de checkout.session.completed: {obj}")
            stripe_sub_id = obj.get("subscription")
            customer_id = obj.get("customer")

            suscripcion = db.query(SuscripcionSuscriptor).join(Suscriptor).filter(
                SuscripcionSuscriptor.stripe_subscription_id == None,
                Suscriptor.stripe_customer_id == customer_id
            ).first()

            if suscripcion and stripe_sub_id:
                suscripcion.stripe_subscription_id = stripe_sub_id
                suscripcion.estado = "activo"
                suscripcion.suscriptor.estado = "activo"  # <-- ACTIVAMOS EL SUSCRIPTOR
                db.commit()
                print(f"Suscripción activada en checkout.session.completed: {stripe_sub_id}")
            else:
                print(f"No se encontró suscripción pendiente o falta subscription_id en checkout.session.completed")

        elif event_type == "invoice.paid":
            print(f"Payload completo de invoice.paid: {obj}")
            stripe_sub_id = (
                obj.get("subscription") or
                (obj.get("parent", {}).get("subscription_details", {}).get("subscription"))
            )

            if not stripe_sub_id:
                print("invoice.paid recibido pero sin subscription ID. Revisa el payload arriba.")
                return {"status": "ignored"}

            suscripcion = db.query(SuscripcionSuscriptor).filter_by(stripe_subscription_id=stripe_sub_id).first()
            if suscripcion:
                suscripcion.estado = "activo"
                suscripcion.suscriptor.estado = "activo"  # <-- ACTIVAMOS EL SUSCRIPTOR
                db.commit()
                print(f"Suscripción activada en invoice.paid: {stripe_sub_id}")
            else:
                print(f"No se encontró suscripción con stripe_subscription_id={stripe_sub_id}")

        elif event_type == "customer.subscription.deleted":
            print(f"Payload completo de customer.subscription.deleted: {obj}")
            stripe_sub_id = obj.get("id")
            if not stripe_sub_id:
                print("customer.subscription.deleted recibido pero sin ID")
                return {"status": "ignored"}

            suscripcion = db.query(SuscripcionSuscriptor).filter_by(stripe_subscription_id=stripe_sub_id).first()
            if suscripcion:
                suscripcion.estado = "inactivo"
                suscripcion.suscriptor.estado = "inactivo"  # <-- DESACTIVAMOS EL SUSCRIPTOR
                db.commit()
                print(f"Suscripción inactivada: {stripe_sub_id}")
            else:
                print(f"No se encontró suscripción con stripe_subscription_id={stripe_sub_id}")

    except Exception as e:
        print(f"Error procesando evento: {e}")
        raise HTTPException(status_code=500, detail="Error procesando evento")

    return {"status": "success"}
