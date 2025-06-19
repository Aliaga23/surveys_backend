import stripe
from app.models import Suscriptor, PlanSuscripcion, SuscripcionSuscriptor
from datetime import datetime
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

def crear_suscripcion_stripe(db, suscriptor_id, plan_id):
    suscriptor = db.query(Suscriptor).filter_by(id=suscriptor_id).first()
    plan = db.query(PlanSuscripcion).filter_by(id=plan_id).first()

    if not suscriptor or not plan:
        raise Exception("Suscriptor o plan no encontrado")

    if not suscriptor.stripe_customer_id:
        customer = stripe.Customer.create(
            email=suscriptor.email,
            name=suscriptor.nombre
        )
        suscriptor.stripe_customer_id = customer.id
        db.commit()

    # Crear la suscripción en Stripe
    subscription = stripe.Subscription.create(
        customer=suscriptor.stripe_customer_id,
        items=[{"price": plan.stripe_price_id}],
        payment_behavior="default_incomplete",
        expand=["latest_invoice.payment_intent"]
    )

    nueva_suscripcion = SuscripcionSuscriptor(
        suscriptor_id=suscriptor.id,
        plan_id=plan.id,
        inicia_en=datetime.utcnow(),
        estado="pendiente",
        stripe_subscription_id=subscription.id
    )
    db.add(nueva_suscripcion)
    db.commit()

    checkout_url = subscription["latest_invoice"]["hosted_invoice_url"]
    return {"checkout_url": checkout_url}
