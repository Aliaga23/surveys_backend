# app/models/survey.py
import uuid
from sqlalchemy import (
    Column, Text, Integer, Boolean, TIMESTAMP, ForeignKey, Numeric, UniqueConstraint,String
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base
from sqlalchemy.orm import relationship

class PlantillaEncuesta(Base):
    __tablename__ = "plantilla_encuesta"
    id            = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suscriptor_id = Column(PGUUID(as_uuid=True), ForeignKey("suscriptor.id", ondelete="CASCADE"), nullable=False)
    nombre        = Column(Text, nullable=False)
    descripcion   = Column(Text)
    activo        = Column(Boolean, default=True)
    creado_en     = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relaciones
    preguntas = relationship("PreguntaEncuesta", back_populates="plantilla", cascade="all, delete-orphan")
    campanas = relationship("CampanaEncuesta", back_populates="plantilla")

class PreguntaEncuesta(Base):
    __tablename__ = "pregunta_encuesta"
    id               = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plantilla_id     = Column(PGUUID(as_uuid=True), ForeignKey("plantilla_encuesta.id", ondelete="CASCADE"), nullable=False)
    orden            = Column(Integer, nullable=False)
    texto            = Column(Text, nullable=False)
    tipo_pregunta_id = Column(Integer, ForeignKey("tipo_pregunta.id"), nullable=False)
    obligatorio      = Column(Boolean, default=True)
    
    __table_args__ = (
        UniqueConstraint('plantilla_id', 'orden'),
    )

    # Relaciones
    plantilla = relationship("PlantillaEncuesta", back_populates="preguntas")
    opciones = relationship("OpcionEncuesta", back_populates="pregunta", cascade="all, delete-orphan")

class OpcionEncuesta(Base):
    __tablename__ = "opcion_encuesta"
    id          = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregunta_id = Column(PGUUID(as_uuid=True), ForeignKey("pregunta_encuesta.id", ondelete="CASCADE"), nullable=False)
    texto       = Column(Text, nullable=False)
    valor       = Column(Text)
    
    __table_args__ = (
        UniqueConstraint('pregunta_id', 'valor'),
    )

    # Relaciones
    pregunta = relationship("PreguntaEncuesta", back_populates="opciones")

class CampanaEncuesta(Base):
    __tablename__ = "campana_encuesta"
    id            = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suscriptor_id = Column(PGUUID(as_uuid=True), ForeignKey("suscriptor.id", ondelete="CASCADE"), nullable=False)
    plantilla_id  = Column(PGUUID(as_uuid=True), ForeignKey("plantilla_encuesta.id", ondelete="SET NULL"))
    nombre        = Column(Text, nullable=False)
    canal_id      = Column(Integer, ForeignKey("canal.id"), nullable=False)
    programada_en = Column(TIMESTAMP(timezone=True))
    estado_id     = Column(Integer, ForeignKey("estado_campana.id"), default=1)
    creado_en     = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relaciones
    entregas = relationship("EntregaEncuesta", back_populates="campana", cascade="all, delete-orphan")
    plantilla = relationship("PlantillaEncuesta")
    
class Destinatario(Base):
    __tablename__ = "destinatario"
    id            = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suscriptor_id = Column(PGUUID(as_uuid=True), ForeignKey("suscriptor.id", ondelete="CASCADE"), nullable=False)
    nombre        = Column(Text)
    telefono      = Column(Text)
    email         = Column(Text)
    creado_en     = Column(TIMESTAMP(timezone=True), server_default=func.now())

class EntregaEncuesta(Base):
    __tablename__ = "entrega_encuesta"
    id              = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campana_id      = Column(PGUUID(as_uuid=True), ForeignKey("campana_encuesta.id", ondelete="CASCADE"), nullable=False)
    destinatario_id = Column(PGUUID(as_uuid=True), ForeignKey("destinatario.id", ondelete="CASCADE"), nullable=True)
    canal_id        = Column(Integer, ForeignKey("canal.id"), nullable=False)
    estado_id       = Column(Integer, ForeignKey("estado_entrega.id"), default=1)
    enviado_en      = Column(TIMESTAMP(timezone=True))
    respondido_en   = Column(TIMESTAMP(timezone=True))

    # Relaciones
    campana = relationship("CampanaEncuesta", back_populates="entregas")
    destinatario = relationship("Destinatario")
    respuestas = relationship("RespuestaEncuesta", back_populates="entrega", cascade="all, delete-orphan")
    conversacion = relationship("ConversacionEncuesta", back_populates="entrega", cascade="all, delete-orphan")
    vapi_calls = relationship("VapiCallRelation", back_populates="entrega", cascade="all, delete-orphan")

class RespuestaEncuesta(Base):
    __tablename__ = "respuesta_encuesta"
    id          = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entrega_id  = Column(PGUUID(as_uuid=True), ForeignKey("entrega_encuesta.id", ondelete="CASCADE"), nullable=False)
    recibido_en = Column(TIMESTAMP(timezone=True), server_default=func.now())
    puntuacion  = Column(Numeric(5,2))
    raw_payload = Column(JSONB)

    # Relaciones
    entrega = relationship("EntregaEncuesta", back_populates="respuestas")
    respuestas_preguntas = relationship("RespuestaPregunta", back_populates="respuesta", cascade="all, delete-orphan")

class RespuestaPregunta(Base):
    __tablename__ = "respuesta_pregunta"
    id           = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    respuesta_id = Column(PGUUID(as_uuid=True), ForeignKey("respuesta_encuesta.id", ondelete="CASCADE"), nullable=False)
    pregunta_id  = Column(PGUUID(as_uuid=True), ForeignKey("pregunta_encuesta.id", ondelete="CASCADE"), nullable=False)
    texto        = Column(Text)
    numero       = Column(Numeric)
    opcion_id    = Column(PGUUID(as_uuid=True), ForeignKey("opcion_encuesta.id", ondelete="SET NULL"))
    metadatos    = Column(JSONB, default=lambda: {}) 

    respuesta = relationship("RespuestaEncuesta", back_populates="respuestas_preguntas")

class ConversacionEncuesta(Base):
    __tablename__ = "conversacion_encuesta"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entrega_id = Column(PGUUID(as_uuid=True), ForeignKey("entrega_encuesta.id", ondelete="CASCADE"), nullable=False)
    historial = Column(JSONB, default=list)
    pregunta_actual_id = Column(PGUUID(as_uuid=True), ForeignKey("pregunta_encuesta.id"))
    completada = Column(Boolean, default=False)
    creado_en = Column(TIMESTAMP(timezone=True), server_default=func.now())

    entrega = relationship("EntregaEncuesta", back_populates="conversacion")
    pregunta_actual = relationship("PreguntaEncuesta")

class VapiCallRelation(Base):
    """Relación entre llamadas de Vapi y entregas de encuesta"""
    __tablename__ = "vapi_call_relation"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entrega_id = Column(PGUUID(as_uuid=True), ForeignKey("entrega_encuesta.id", ondelete="CASCADE"), nullable=False)
    call_id = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relación
    entrega = relationship("EntregaEncuesta", back_populates="vapi_calls")

class RespuestaTemp(Base):
    """
    Modelo temporal para guardar respuestas durante la conversación
    """
    __tablename__ = "respuesta_temp"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entrega_id = Column(PGUUID(as_uuid=True), ForeignKey("entrega_encuesta.id", ondelete="CASCADE"), nullable=False)
    pregunta_id = Column(PGUUID(as_uuid=True), ForeignKey("pregunta_encuesta.id", ondelete="CASCADE"), nullable=False)
    texto = Column(Text, nullable=True)
    numero = Column(Numeric, nullable=True)
    opcion_id = Column(PGUUID(as_uuid=True), ForeignKey("opcion_encuesta.id", ondelete="SET NULL"), nullable=True)
    creado_en = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Índice para búsquedas rápidas
    __table_args__ = (
        UniqueConstraint('entrega_id', 'pregunta_id', 'opcion_id', name='unique_respuesta_temp'),
    )
