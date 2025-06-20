from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from uuid import UUID
import jwt
from datetime import datetime
from typing import Dict, List

from app.core.database import get_db
from app.core.config import settings
from app.services.shared_service import get_entrega_con_plantilla
from app.services.respuestas_service import create_respuesta
from app.services.entregas_service import mark_as_responded
from app.core.constants import ESTADO_RESPONDIDO
from app.schemas.respuestas_schema import RespuestaCreateEmail, RespuestaEncuestaCreate, RespuestaPreguntaCreate

router = APIRouter(
    prefix="/encuestas",
    tags=["Encuestas Públicas"]
)

@router.get("/verificar/{token}")
async def verificar_token(token: str, db: Session = Depends(get_db)):
    """
    Verifica la validez de un token de encuesta y devuelve los detalles
    de la entrega si es válido
    """
    try:
        # Decodificar el token
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        entrega_id = UUID(payload["sub"])
        
        # Verificar que la entrega existe y está activa
        entrega = get_entrega_con_plantilla(db, entrega_id)
        if not entrega:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Encuesta no encontrada"
            )
        
        # Verificar que la entrega no haya sido respondida ya
        if entrega.estado_id == ESTADO_RESPONDIDO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta encuesta ya ha sido respondida"
            )
        
        # Devolver los datos necesarios para mostrar la encuesta
        return {
            "entrega_id": str(entrega.id),
            "campana": {
                "id": str(entrega.campana.id),
                "nombre": entrega.campana.nombre
            },
            "plantilla": {
                "id": str(entrega.campana.plantilla.id),
                "nombre": entrega.campana.plantilla.nombre,
                "descripcion": entrega.campana.plantilla.descripcion,
                "preguntas": [{
                    "id": str(pregunta.id),
                    "texto": pregunta.texto,
                    "tipo_pregunta_id": pregunta.tipo_pregunta_id,
                    "obligatorio": pregunta.obligatorio,
                    "orden": pregunta.orden,
                    "opciones": [{
                        "id": str(opcion.id),
                        "texto": opcion.texto,
                        "valor": opcion.valor
                    } for opcion in pregunta.opciones] if hasattr(pregunta, 'opciones') else []
                } for pregunta in sorted(entrega.campana.plantilla.preguntas, key=lambda x: x.orden)]
            },
            "destinatario": {
                "nombre": entrega.destinatario.nombre,
                "email": entrega.destinatario.email
            }
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El enlace de la encuesta ha expirado"
        )
    except (jwt.InvalidTokenError, ValueError):  # Usar InvalidTokenError en lugar de JWTError
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )

@router.post("/responder/{token}")
async def responder_encuesta(
    token: str, 
    respuestas: List[RespuestaCreateEmail] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Recibe y guarda las respuestas de una encuesta por email
    """
    try:
        # Decodificar el token para obtener el ID de la entrega
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        entrega_id = UUID(payload["sub"])
        
        # Verificar que la entrega existe y no ha sido respondida
        entrega = get_entrega_con_plantilla(db, entrega_id)
        if not entrega:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Encuesta no encontrada"
            )
            
        if entrega.estado_id == ESTADO_RESPONDIDO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta encuesta ya ha sido respondida"
            )
            
        # Convertir respuestas del formato email al formato esperado por create_respuesta
        respuestas_preguntas = []
        
        for r in respuestas:
            pregunta_id = UUID(r.pregunta_id)
            
            if r.tipo_respuesta == "texto" and r.texto is not None:
                # Para respuestas de texto
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta_id,
                    texto=r.texto,
                    metadatos={}
                )
                respuestas_preguntas.append(respuesta_pregunta)
                
            elif r.tipo_respuesta == "numero" and r.numero is not None:
                # Para respuestas numéricas
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta_id,
                    numero=r.numero,
                    metadatos={}
                )
                respuestas_preguntas.append(respuesta_pregunta)
                
            elif r.tipo_respuesta == "opcion" and r.opcion_id is not None:
                # Para selección única
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta_id,
                    opcion_id=UUID(r.opcion_id),
                    metadatos={}
                )
                respuestas_preguntas.append(respuesta_pregunta)
                
            elif r.tipo_respuesta == "opciones" and r.opciones_ids:
                # Para selección múltiple - crear una respuesta por cada opción seleccionada
                for opcion_id in r.opciones_ids:
                    respuesta_pregunta = RespuestaPreguntaCreate(
                        pregunta_id=pregunta_id,
                        opcion_id=UUID(opcion_id),
                        metadatos={}
                    )
                    respuestas_preguntas.append(respuesta_pregunta)
        
        respuesta_data = RespuestaEncuestaCreate(
            respuestas_preguntas=respuestas_preguntas
        )
        
        respuesta_encuesta = create_respuesta(db, entrega_id, respuesta_data)
        
        
        entrega_actualizada = get_entrega_con_plantilla(db, entrega_id)
        if entrega_actualizada.estado_id != ESTADO_RESPONDIDO:
            mark_as_responded(db, entrega_id)
        
        return {
            "status": "success",
            "message": "Respuestas guardadas correctamente",
            "respuesta_id": str(respuesta_encuesta.id)
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El enlace de la encuesta ha expirado"
        )
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando las respuestas: {str(e)}"
        )