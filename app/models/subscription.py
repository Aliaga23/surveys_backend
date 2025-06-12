import uuid
from sqlalchemy import Column, Integer, Text, Numeric, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func

from app.core.database import Base

class PlanSuscripcion(Base):
    __tablename__ = "plan_suscripcion"
    id             = Column(Integer, primary_key=True, index=True)
    nombre         = Column(Text, unique=True, nullable=False)
    precio_mensual = Column(Numeric(10,2), nullable=False)
    descripcion    = Column(Text)
    creado_en      = Column(TIMESTAMP(timezone=True), server_default=func.now())

class SuscripcionSuscriptor(Base):
    __tablename__ = "suscripcion_suscriptor"
    id             = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suscriptor_id  = Column(PGUUID(as_uuid=True), ForeignKey("suscriptor.id", ondelete="CASCADE"), nullable=False)
    plan_id        = Column(Integer, ForeignKey("plan_suscripcion.id"), nullable=False)
    inicia_en      = Column(TIMESTAMP(timezone=True), nullable=False)
    expira_en      = Column(TIMESTAMP(timezone=True))
    estado         = Column(Text, nullable=False, default="activo")
