import uuid
from sqlalchemy import Column, Text, Boolean, TIMESTAMP, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class CuentaUsuario(Base):
    __tablename__ = "cuenta_usuario"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suscriptor_id = Column(PGUUID(as_uuid=True), ForeignKey("suscriptor.id", ondelete="CASCADE"))
    email = Column(Text, nullable=False)
    password_hash = Column(Text, nullable=False)
    nombre_completo = Column(Text, nullable=False)
    rol_id = Column(Integer, ForeignKey("rol.id"), nullable=False, default=2)
    activo = Column(Boolean, default=True)
    creado_en = Column(TIMESTAMP(timezone=True), server_default="now()")

    suscriptor = relationship("Suscriptor", back_populates="usuarios")
    rol = relationship("Rol")
