# app/services/entregas_service.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.constants import (
    ESTADO_ENVIADO,
    ESTADO_FALLIDO,
    ESTADO_PENDIENTE,
    ESTADO_RESPONDIDO,
)
from app.models.survey import (
    Destinatario,
    EntregaEncuesta,
    PreguntaEncuesta,
    PlantillaEncuesta,
)
from app.models.suscriptor import Suscriptor
from app.services import whatsapp_service as ws
from app.services.email_service import enviar_email
from app.services.shared_service import get_entrega_con_plantilla
from app.services.vapi_service import crear_llamada_encuesta
from app.schemas.entregas_schema import EntregaCreate, EntregaUpdate

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# HELPERS TOKEN / URL
# --------------------------------------------------------------------------- #


def _generar_token_encuesta(entrega_id: UUID) -> str:
    expiration = datetime.utcnow() + timedelta(days=settings.SURVEY_LINK_EXPIRY_DAYS)
    payload = {"sub": str(entrega_id), "exp": expiration}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _generar_url_encuesta(entrega_id: UUID) -> str:
    return f"{settings.FRONTEND_URL}/encuestas/{_generar_token_encuesta(entrega_id)}"


# --------------------------------------------------------------------------- #
# CRUD BÁSICO
# --------------------------------------------------------------------------- #


def get_entrega(db: Session, entrega_id: UUID) -> Optional[EntregaEncuesta]:
    return (
        db.query(EntregaEncuesta)
        .options(
            joinedload(EntregaEncuesta.destinatario),
            joinedload(EntregaEncuesta.respuestas),
            joinedload(EntregaEncuesta.conversacion),
        )
        .filter(EntregaEncuesta.id == entrega_id)
        .first()
    )


def list_entregas(
    db: Session, campana_id: UUID, skip: int = 0, limit: int = 100
) -> List[EntregaEncuesta]:
    return (
        db.query(EntregaEncuesta)
        .filter(EntregaEncuesta.campana_id == campana_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_entrega(
    db: Session, entrega_id: UUID, payload: EntregaUpdate
) -> Optional[EntregaEncuesta]:
    entrega = get_entrega(db, entrega_id)
    if not entrega:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entrega, field, value)
    db.commit()
    db.refresh(entrega)
    return entrega


def delete_entrega(db: Session, entrega_id: UUID) -> bool:
    entrega = get_entrega(db, entrega_id)
    if not entrega:
        return False
    db.delete(entrega)
    db.commit()
    return True


# --------------------------------------------------------------------------- #
# CAMBIOS DE ESTADO
# --------------------------------------------------------------------------- #


def mark_as_sent(db: Session, entrega_id: UUID) -> Optional[EntregaEncuesta]:
    ent = get_entrega(db, entrega_id)
    if not ent:
        return None
    if ent.estado_id != ESTADO_PENDIENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede marcar como enviada. Estado actual: {ent.estado_id}",
        )
    ent.estado_id = ESTADO_ENVIADO
    ent.enviado_en = datetime.now()
    db.commit()
    db.refresh(ent)
    return ent


def mark_as_responded(db: Session, entrega_id: UUID) -> Optional[EntregaEncuesta]:
    ent = get_entrega(db, entrega_id)
    if not ent:
        return None
    if ent.estado_id not in (ESTADO_PENDIENTE, ESTADO_ENVIADO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede marcar como respondida. Estado actual: {ent.estado_id}",
        )
    ent.estado_id = ESTADO_RESPONDIDO
    ent.respondido_en = datetime.now()
    db.commit()
    db.refresh(ent)
    return ent


def mark_as_failed(
    db: Session, entrega_id: UUID, reason: str | None = None
) -> Optional[EntregaEncuesta]:
    ent = get_entrega(db, entrega_id)
    if not ent:
        return None
    ent.estado_id = ESTADO_FALLIDO
    db.commit()
    db.refresh(ent)
    if reason:
        logger.error("Entrega %s marcada como fallida: %s", entrega_id, reason)
    return ent


# --------------------------------------------------------------------------- #
# BUSCAR ENTREGA POR DESTINATARIO
# --------------------------------------------------------------------------- #


def get_entrega_by_destinatario(
    db: Session, *, email: str | None = None, telefono: str | None = None
) -> Optional[EntregaEncuesta]:
    if not email and not telefono:
        return None

    q = (
        db.query(EntregaEncuesta)
        .join(EntregaEncuesta.destinatario)
        .options(joinedload(EntregaEncuesta.conversacion))
    )

    if email:
        q = q.filter(Destinatario.email == email)
    if telefono:
        t_clean = telefono.split("@")[0] if "@" in telefono else telefono
        q = q.filter(Destinatario.telefono.contains(t_clean))

    return q.order_by(EntregaEncuesta.enviado_en.desc().nullslast()).first()


# --------------------------------------------------------------------------- #
# CREACIÓN Y ENVÍO DE ENTREGAS (async)
# --------------------------------------------------------------------------- #


async def create_entrega(
    db: Session,
    campana_id: UUID,
    payload: EntregaCreate,
) -> EntregaEncuesta:
    """
    Canal 1 → Email
    Canal 2 → WhatsApp
    Canal 3 → Vapi
    Canal 4 → Papel (no envía nada; sin destinatario)
    """
    # ─── Validación destinatario según canal ────────────────────────────
    if payload.canal_id != 4 and payload.destinatario_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="destinatario_id requerido para este canal",
        )

    entrega = EntregaEncuesta(
        **payload.model_dump(),
        campana_id=campana_id,
        estado_id=ESTADO_PENDIENTE,
    )
    db.add(entrega)
    db.commit()
    db.refresh(entrega)

    # ------------------------------------------------------------------ #
    # CANAL PAPEL  (NO envía nada)                                       #
    # ------------------------------------------------------------------ #
    if payload.canal_id == 4:
        # Queda en PENDIENTE; luego se imprimirá con QR.
        return entrega

    # ------------------------------------------------------------------ #
    # CANAL EMAIL                                                        #
    # ------------------------------------------------------------------ #
    if payload.canal_id == 1:
        try:
            entrega = get_entrega_con_plantilla(db, entrega.id)
            if not entrega.destinatario.email:
                raise ValueError("El destinatario no tiene email")

            suscriptor: Suscriptor | None = db.get(
                Suscriptor, entrega.campana.suscriptor_id
            )
            if not suscriptor:
                raise ValueError("No se encontró el suscriptor")

            await enviar_email(
                destinatario_email=entrega.destinatario.email,
                destinatario_nombre=entrega.destinatario.nombre or "Estimado/a",
                asunto=f"Te invitamos a responder una encuesta: {entrega.campana.nombre}",
                nombre_campana=entrega.campana.nombre,
                nombre_empresa=suscriptor.nombre,
                url_encuesta=_generar_url_encuesta(entrega.id),
            )

            entrega.estado_id = ESTADO_ENVIADO
            entrega.enviado_en = datetime.now()
            db.commit()
            db.refresh(entrega)

        except Exception as exc:
            mark_as_failed(db, entrega.id, str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error enviando email: {exc}",
            ) from exc

    # ------------------------------------------------------------------ #
    # CANAL WHATSAPP                                                     #
    # ------------------------------------------------------------------ #
    elif payload.canal_id == 2:
        try:
            entrega = get_entrega_con_plantilla(db, entrega.id)
            if not entrega.destinatario.telefono:
                raise ValueError("El destinatario no tiene teléfono")

            saludo = (
                f"¡Hola {entrega.destinatario.nombre or 'estimado/a'}! 👋\n\n"
                f"Soy el asistente virtual de {entrega.campana.nombre}. "
                "Tenemos una encuesta breve que nos gustaría que completes."
            )
            await ws.send_confirm(entrega.destinatario.telefono, saludo)

            entrega.estado_id = ESTADO_ENVIADO
            entrega.enviado_en = datetime.now()
            db.commit()
            db.refresh(entrega)

            # registrar estado inicial en cache en memoria
            try:
                from app.routers.whatsapp_router import conversaciones_estado  # noqa
                num = (
                    entrega.destinatario.telefono.split("@")[0]
                    if "@c.us" in entrega.destinatario.telefono
                    else entrega.destinatario.telefono
                )
                conversaciones_estado[num] = "esperando_confirmacion"
            except Exception:
                logger.debug("No se pudo registrar conversaciones_estado", exc_info=True)

        except Exception as exc:
            mark_as_failed(db, entrega.id, str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error iniciando conversación: {exc}",
            ) from exc

    # ------------------------------------------------------------------ #
    # CANAL VAPI (LLAMADA)                                               #
    # ------------------------------------------------------------------ #
    elif payload.canal_id == 3:
        try:
            entrega = get_entrega_con_plantilla(db, entrega.id)
            if not entrega.destinatario.telefono:
                raise ValueError("El destinatario no tiene teléfono")

            preguntas: List[dict] = []
            if entrega.campana and entrega.campana.plantilla:
                for p in entrega.campana.plantilla.preguntas:
                    preguntas.append(
                        {
                            "id": str(p.id),
                            "texto": p.texto,
                            "tipo_pregunta_id": p.tipo_pregunta_id,
                            "obligatorio": p.obligatorio,
                            "opciones": [
                                {"id": str(o.id), "texto": o.texto, "valor": o.valor}
                                for o in getattr(p, "opciones", [])
                            ],
                        }
                    )

            await crear_llamada_encuesta(
                db=db,
                entrega_id=entrega.id,
                telefono=entrega.destinatario.telefono,
                nombre_destinatario=entrega.destinatario.nombre or "Cliente",
                campana_nombre=entrega.campana.nombre,
                preguntas=preguntas,
            )

            entrega.estado_id = ESTADO_ENVIADO
            entrega.enviado_en = datetime.now()
            db.commit()
            db.refresh(entrega)

        except Exception as exc:
            mark_as_failed(db, entrega.id, str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error iniciando llamada: {exc}",
            ) from exc

    return entrega


# --------------------------------------------------------------------------- #
# BULK DE ENTREGAS PAPEL                                                     #
# --------------------------------------------------------------------------- #


def create_bulk_entregas_papel(
    db: Session,
    campana_id: UUID,
    cantidad: int,
) -> List[EntregaEncuesta]:
    entregas: list[EntregaEncuesta] = []
    now = datetime.now()  # Obtener hora actual para todas las entregas
    
    for _ in range(cantidad):
        e = EntregaEncuesta(
            campana_id=campana_id,
            canal_id=4,
            destinatario_id=None,
            estado_id=ESTADO_ENVIADO,
            enviado_en=now  # Añadimos la fecha de creación
        )
        db.add(e)
        entregas.append(e)
    db.commit()
    for e in entregas:
        db.refresh(e)
    return entregas


def create_bulk_entregas_audio(
    db: Session, campana_id: UUID, cantidad: int
) -> List[EntregaEncuesta]:
    entregas = []
    now = datetime.now()  # Obtener hora actual para todas las entregas
    for _ in range(cantidad):
        e = EntregaEncuesta(
            campana_id=campana_id,
            canal_id=5,                 
            destinatario_id=None,
            estado_id=ESTADO_ENVIADO,
            enviado_en=now
        )
        db.add(e)
        entregas.append(e)
    db.commit()
    for e in entregas:
        db.refresh(e)
    return entregas
