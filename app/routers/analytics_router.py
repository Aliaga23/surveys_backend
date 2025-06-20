from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, List
from sqlalchemy import func, case
from sqlalchemy.sql.expression import case

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.models.survey import (
    CampanaEncuesta, EntregaEncuesta, RespuestaEncuesta, PlantillaEncuesta,
    PreguntaEncuesta, OpcionEncuesta, Destinatario, ConversacionEncuesta
)
from app.models.catalogos import Canal, EstadoEntrega, EstadoCampana, TipoPregunta
from app.models.cuenta_usuario import CuentaUsuario
from app.core.constants import (
    ESTADO_PENDIENTE, ESTADO_ENVIADO, ESTADO_RESPONDIDO, ESTADO_FALLIDO,
)

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/dashboard")
async def get_suscriptor_dashboard(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Devuelve un dashboard completo con todas las estadísticas para el suscriptor autenticado
    """
    if token_data.role == "empresa":
        suscriptor_id = UUID(token_data.sub)
    elif token_data.role == "operator":
        cuenta = db.query(CuentaUsuario).filter(CuentaUsuario.id == UUID(token_data.sub)).first()
        if not cuenta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cuenta de usuario no encontrada"
            )
        suscriptor_id = cuenta.suscriptor_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para acceder a estos datos"
        )
    
    plantillas_query = db.query(PlantillaEncuesta).filter(
        PlantillaEncuesta.suscriptor_id == suscriptor_id
    )
    total_plantillas = plantillas_query.count()
    plantillas_activas = plantillas_query.filter(PlantillaEncuesta.activo == True).count()
    
    preguntas_por_tipo = db.query(
        TipoPregunta.nombre,
        func.count(PreguntaEncuesta.id).label("total")
    ).join(
        PreguntaEncuesta, PreguntaEncuesta.tipo_pregunta_id == TipoPregunta.id
    ).join(
        PlantillaEncuesta, PlantillaEncuesta.id == PreguntaEncuesta.plantilla_id
    ).filter(
        PlantillaEncuesta.suscriptor_id == suscriptor_id
    ).group_by(
        TipoPregunta.nombre
    ).all()
    
    campanas_query = db.query(CampanaEncuesta).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id
    )
    total_campanas = campanas_query.count()
    
    campanas_por_estado = db.query(
        EstadoCampana.nombre,
        func.count(CampanaEncuesta.id).label("total")
    ).join(
        CampanaEncuesta, CampanaEncuesta.estado_id == EstadoCampana.id
    ).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id
    ).group_by(
        EstadoCampana.nombre
    ).all()
    
    entregas_query = db.query(EntregaEncuesta).join(
        CampanaEncuesta, CampanaEncuesta.id == EntregaEncuesta.campana_id
    ).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id
    )
    total_entregas = entregas_query.count()
    
    entregas_por_estado = db.query(
        EstadoEntrega.nombre,
        func.count(EntregaEncuesta.id).label("total")
    ).join(
        EntregaEncuesta, EntregaEncuesta.estado_id == EstadoEntrega.id
    ).join(
        CampanaEncuesta, CampanaEncuesta.id == EntregaEncuesta.campana_id
    ).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id
    ).group_by(
        EstadoEntrega.nombre
    ).all()
    
    entregas_por_canal = db.query(
        Canal.nombre,
        func.count(EntregaEncuesta.id).label("total")
    ).join(
        EntregaEncuesta, EntregaEncuesta.canal_id == Canal.id
    ).join(
        CampanaEncuesta, CampanaEncuesta.id == EntregaEncuesta.campana_id
    ).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id
    ).group_by(
        Canal.nombre
    ).all()
    
    total_respuestas = db.query(RespuestaEncuesta).join(
        EntregaEncuesta, EntregaEncuesta.id == RespuestaEncuesta.entrega_id
    ).join(
        CampanaEncuesta, CampanaEncuesta.id == EntregaEncuesta.campana_id
    ).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id
    ).count()
    
    tasa_respuesta = (total_respuestas / total_entregas * 100) if total_entregas > 0 else 0
    
    campanas_exitosas = db.query(
        CampanaEncuesta.id,
        CampanaEncuesta.nombre,
        func.count(EntregaEncuesta.id).label("total_entregas"),
        func.sum(case(
            (EntregaEncuesta.estado_id == ESTADO_RESPONDIDO, 1), 
            else_=0
        )).label("total_respondidas")
    ).join(
        EntregaEncuesta, EntregaEncuesta.campana_id == CampanaEncuesta.id
    ).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id
    ).group_by(
        CampanaEncuesta.id, CampanaEncuesta.nombre
    ).having(
        func.count(EntregaEncuesta.id) > 0
    ).all()
    
    campanas_con_tasa = []
    for c in campanas_exitosas:
        tasa = (c.total_respondidas / c.total_entregas * 100) if c.total_entregas > 0 else 0
        campanas_con_tasa.append({
            "id": str(c.id),
            "nombre": c.nombre,
            "total_entregas": c.total_entregas,
            "total_respondidas": c.total_respondidas,
            "tasa_respuesta": round(tasa, 2)
        })
    
    campanas_con_tasa.sort(key=lambda x: x["tasa_respuesta"], reverse=True)
    
    total_destinatarios = db.query(Destinatario).filter(
        Destinatario.suscriptor_id == suscriptor_id
    ).count()
    
    destinatarios_completos = db.query(Destinatario).filter(
        Destinatario.suscriptor_id == suscriptor_id,
        Destinatario.email.isnot(None),
        Destinatario.telefono.isnot(None)
    ).count()
    
    total_conversaciones = db.query(ConversacionEncuesta).join(
        EntregaEncuesta, EntregaEncuesta.id == ConversacionEncuesta.entrega_id
    ).join(
        CampanaEncuesta, CampanaEncuesta.id == EntregaEncuesta.campana_id
    ).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id
    ).count()
    
    conversaciones_completadas = db.query(ConversacionEncuesta).join(
        EntregaEncuesta, EntregaEncuesta.id == ConversacionEncuesta.entrega_id
    ).join(
        CampanaEncuesta, CampanaEncuesta.id == EntregaEncuesta.campana_id
    ).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id,
        ConversacionEncuesta.completada == True
    ).count()
    
    # Retornar todos los datos consolidados
    return {
        "suscriptor_id": str(suscriptor_id),
        "resumen_general": {
            "total_plantillas": total_plantillas,
            "plantillas_activas": plantillas_activas,
            "total_campanas": total_campanas,
            "total_entregas": total_entregas,
            "total_respuestas": total_respuestas,
            "tasa_respuesta_global": round(tasa_respuesta, 2),
            "total_destinatarios": total_destinatarios,
            "destinatarios_completos": destinatarios_completos
        },
        "campanas": {
            "total": total_campanas,
            "por_estado": {estado.nombre: estado.total for estado in campanas_por_estado},
            "top_exitosas": campanas_con_tasa[:5]  # Top 5 campañas
        },
        "entregas": {
            "total": total_entregas,
            "por_estado": {estado.nombre: estado.total for estado in entregas_por_estado},
            "por_canal": {canal.nombre: canal.total for canal in entregas_por_canal}
        },
        "respuestas": {
            "total": total_respuestas,
            "tasa_global": round(tasa_respuesta, 2)
        },
        "preguntas": {
            "por_tipo": {tipo.nombre: tipo.total for tipo in preguntas_por_tipo}
        },
        "conversaciones": {
            "total": total_conversaciones,
            "completadas": conversaciones_completadas,
            "tasa_completitud": round((conversaciones_completadas / total_conversaciones * 100) if total_conversaciones > 0 else 0, 2)
        }
    }