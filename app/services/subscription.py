import stripe
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor
from app.schemas.subscription import (
    PlanSuscripcionCreate, PlanSuscripcionUpdate,
    SuscripcionSuscriptorCreate, SuscripcionSuscriptorUpdate
)
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

# ---------------- PlanSuscripcion ----------------

def get_plan(db: Session, plan_id: int) -> PlanSuscripcion | None:
    return db.get(PlanSuscripcion, plan_id)

def list_planes(db: Session) -> List[PlanSuscripcion]:
    return db.query(PlanSuscripcion).all()

def create_plan(db: Session, payload: PlanSuscripcionCreate) -> PlanSuscripcion:
    # Crear producto en Stripe
    product = stripe.Product.create(name=payload.nombre)

    # Crear price en Stripe
    price = stripe.Price.create(
        unit_amount=int(payload.precio_mensual * 100),
        currency="usd",  # ajusta a tu moneda
        recurring={"interval": "month"},
        product=product.id
    )

    # Guardar en DB
    plan = PlanSuscripcion(
        nombre=payload.nombre,
        precio_mensual=payload.precio_mensual,
        descripcion=payload.descripcion,
        stripe_price_id=price.id
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

def update_plan(db: Session, plan_id: int, payload: PlanSuscripcionUpdate) -> PlanSuscripcion:
    plan = get_plan(db, plan_id)
    if not plan:
        raise Exception("Plan no encontrado")

    # Recuperar product ID
    price = stripe.Price.retrieve(plan.stripe_price_id)
    product_id = price.product

    # Actualizar producto en Stripe
    stripe.Product.modify(
        product_id,
        name=payload.nombre or plan.nombre,
    )

    # Si cambió el precio, crear nuevo price
    if payload.precio_mensual and payload.precio_mensual != plan.precio_mensual:
        new_price = stripe.Price.create(
            unit_amount=int(payload.precio_mensual * 100),
            currency="usd",
            recurring={"interval": "month"},
            product=product_id
        )
        plan.stripe_price_id = new_price.id
        plan.precio_mensual = payload.precio_mensual

    # Actualizar nombre/desc en DB
    if payload.nombre:
        plan.nombre = payload.nombre
    if payload.descripcion is not None:
        plan.descripcion = payload.descripcion

    db.commit()
    db.refresh(plan)
    return plan

def delete_plan(db: Session, plan_id: int) -> None:
    plan = get_plan(db, plan_id)
    if not plan:
        raise Exception("Plan no encontrado")

    # Archivar en Stripe
    price = stripe.Price.retrieve(plan.stripe_price_id)
    product_id = price.product
    stripe.Product.modify(product_id, active=False)
    stripe.Price.modify(plan.stripe_price_id, active=False)

    # Eliminar en DB
    db.delete(plan)
    db.commit()

# ---------------- SuscripcionSuscriptor (sin cambios) ----------------

def get_suscripcion(db: Session, sus_id: str) -> SuscripcionSuscriptor | None:
    return db.get(SuscripcionSuscriptor, sus_id)

def list_suscripciones(db: Session, suscriptor_id: Optional[str] = None) -> List[SuscripcionSuscriptor]:
    q = db.query(SuscripcionSuscriptor)
    if suscriptor_id:
        q = q.filter_by(suscriptor_id=suscriptor_id)
    return q.all()

def create_suscripcion(db: Session, payload: SuscripcionSuscriptorCreate) -> SuscripcionSuscriptor:
    sus = SuscripcionSuscriptor(**payload.model_dump())
    db.add(sus)
    db.commit()
    db.refresh(sus)
    return sus

def update_suscripcion(db: Session, sus_id: str, payload: SuscripcionSuscriptorUpdate) -> SuscripcionSuscriptor:
    sus = get_suscripcion(db, sus_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sus, k, v)
    db.commit()
    db.refresh(sus)
    return sus

def delete_suscripcion(db: Session, sus_id: str) -> None:
    sus = get_suscripcion(db, sus_id)
    if not sus:
        raise Exception("Suscripción no encontrada")

    # 🔑 Cancelar la suscripción en Stripe si existe
    if sus.stripe_subscription_id:
        try:
            stripe.Subscription.delete(sus.stripe_subscription_id)
        except Exception as e:
            # Esto evita que un error en Stripe bloquee la eliminación en DB
            print(f"Error al cancelar en Stripe: {e}")

    # Eliminar en base de datos
    db.delete(sus)
    db.commit()
