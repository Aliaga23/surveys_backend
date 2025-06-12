from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor
from app.schemas.subscription import (
    PlanSuscripcionCreate, PlanSuscripcionUpdate,
    SuscripcionSuscriptorCreate, SuscripcionSuscriptorUpdate
)

# Ã¢â‚¬â€Ã¢â‚¬â€ PlanSuscripcion Ã¢â‚¬â€Ã¢â‚¬â€
def get_plan(db: Session, plan_id: int) -> PlanSuscripcion | None:
    return db.get(PlanSuscripcion, plan_id)

def list_planes(db: Session) -> List[PlanSuscripcion]:
    return db.query(PlanSuscripcion).all()

def create_plan(db: Session, payload: PlanSuscripcionCreate) -> PlanSuscripcion:
    plan = PlanSuscripcion(**payload.model_dump())
    db.add(plan); db.commit(); db.refresh(plan)
    return plan

def update_plan(db: Session, plan_id: int, payload: PlanSuscripcionUpdate) -> PlanSuscripcion:
    plan = get_plan(db, plan_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(plan, k, v)
    db.commit(); db.refresh(plan)
    return plan

def delete_plan(db: Session, plan_id: int) -> None:
    plan = get_plan(db, plan_id)
    db.delete(plan); db.commit()


# Ã¢â‚¬â€Ã¢â‚¬â€ SuscripcionSuscriptor Ã¢â‚¬â€Ã¢â‚¬â€
def get_suscripcion(db: Session, sus_id: str) -> SuscripcionSuscriptor | None:
    return db.get(SuscripcionSuscriptor, sus_id)

def list_suscripciones(db: Session, suscriptor_id: Optional[str] = None) -> List[SuscripcionSuscriptor]:
    q = db.query(SuscripcionSuscriptor)
    if suscriptor_id:
        q = q.filter_by(suscriptor_id=suscriptor_id)
    return q.all()

def create_suscripcion(db: Session, payload: SuscripcionSuscriptorCreate) -> SuscripcionSuscriptor:
    sus = SuscripcionSuscriptor(**payload.model_dump())
    db.add(sus); db.commit(); db.refresh(sus)
    return sus

def update_suscripcion(db: Session, sus_id: str, payload: SuscripcionSuscriptorUpdate) -> SuscripcionSuscriptor:
    sus = get_suscripcion(db, sus_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sus, k, v)
    db.commit(); db.refresh(sus)
    return sus

def delete_suscripcion(db: Session, sus_id: str) -> None:
    sus = get_suscripcion(db, sus_id)
    db.delete(sus); db.commit()
