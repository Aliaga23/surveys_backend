import uuid
from sqlalchemy import Column, Text, TIMESTAMP, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Administrador(Base):
    __tablename__ = "administrador"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    rol_id = Column(Integer, ForeignKey("rol.id"), nullable=False)
    activo = Column(Boolean, default=True)
    creado_en = Column(TIMESTAMP(timezone=True), server_default="now()")

    rol = relationship("Rol")
