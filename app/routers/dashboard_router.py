from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict
from uuid import UUID

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.schemas.auth import TokenData
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

# Instancia del servicio
dashboard_service = DashboardService(settings.OPENAI_API_KEY)

@router.get("/campaigns/{campaign_id}/analysis")
async def get_campaign_analysis(
    campaign_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict:
    """
    Endpoint para obtener análisis detallado de una campaña usando GPT-4
    """
    try:
        if token_data.role not in ["admin", "empresa"]:
            raise HTTPException(
                status_code=403,
                detail="No tienes permisos para acceder a este análisis"
            )

        # Obtener análisis
        analysis = await dashboard_service.get_campaign_analysis(db, campaign_id)
        
        return analysis

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo análisis de campaña: {str(e)}"
        )