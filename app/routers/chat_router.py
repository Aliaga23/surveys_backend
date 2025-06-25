# app/routers/chat_router.py
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.chat_service import chat_completion

router = APIRouter(prefix="/chat", tags=["Chatbot"])

class ChatIn(BaseModel):
    message: str
    context: Optional[Dict[str, str]] = None   # {"route": "...", "section": "..."}

class ChatOut(BaseModel):
    answer: str
    action_log: List[str]

@router.post("", response_model=ChatOut, status_code=status.HTTP_200_OK)
async def chat_endpoint(
    payload: ChatIn,
    token_data = Depends(get_current_user),  # → TokenData
    db: Session = Depends(get_db),
):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    return await chat_completion(
        db=db,
        token_data=token_data,
        message=payload.message,
        context=payload.context,
    )
