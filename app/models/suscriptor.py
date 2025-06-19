import uuid
from sqlalchemy import Column, Text, TIMESTAMP, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Suscriptor(Base):
    __tablename__ = "suscriptor"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(Text, nullable=False)
    email = Column(Text, nullable=False, unique=True)
    telefono = Column(Text)
    password_hash = Column(Text, nullable=False)
    rol_id = Column(Integer, ForeignKey("rol.id"), nullable=False, default=1)
    estado = Column(Text, default="inactivo")
    creado_en = Column(TIMESTAMP(timezone=True), server_default="now()")
    stripe_customer_id = Column(Text, nullable=True)

    rol = relationship("Rol")
    usuarios = relationship("CuentaUsuario", back_populates="suscriptor")
