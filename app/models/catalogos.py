from sqlalchemy import Column, Integer, String
from app.core.database import Base

class Rol(Base):
    __tablename__ = "rol"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class TipoPregunta(Base):
    __tablename__ = "tipo_pregunta"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class Canal(Base):
    __tablename__ = "canal"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class EstadoCampana(Base):
    __tablename__ = "estado_campana"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class EstadoEntrega(Base):
    __tablename__ = "estado_entrega"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class EstadoDocumento(Base):
    __tablename__ = "estado_documento"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class EstadoPago(Base):
    __tablename__ = "estado_pago"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class MetodoPago(Base):
    __tablename__ = "metodo_pago"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)
