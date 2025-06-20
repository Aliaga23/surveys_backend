from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.services.nlp_service import get_nlp_service, NLPAnalysisService
from app.schemas.nlp_schema import NLPAnalysisRequest, NLPAnalysisResponse

router = APIRouter(
    prefix="/analytics/nlp",
    tags=["NLP Analytics"],
    dependencies=[Depends(get_current_user)]
)

@router.post("/analyze", response_model=NLPAnalysisResponse)
async def analyze_responses(
    params: NLPAnalysisRequest,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Realiza análisis NLP de las respuestas de encuestas para el suscriptor autenticado
    """
    # Obtener el suscriptor_id del token
    suscriptor_id = UUID(token_data.sub)
    
    # Realizar análisis
    nlp_service = get_nlp_service(db)
    return await nlp_service.analyze_responses(suscriptor_id, params)