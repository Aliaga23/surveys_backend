from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel

class Mensaje(BaseModel):
    role: str  # "assistant" o "user"
    content: str
    timestamp: datetime = datetime.now()

class ConversacionBase(BaseModel):
    entrega_id: UUID
    historial: List[Mensaje] = []
    pregunta_actual_id: Optional[UUID] = None
    completada: bool = False

class ConversacionCreate(ConversacionBase):
    pass

class ConversacionUpdate(BaseModel):
    historial: Optional[List[Mensaje]] = None
    pregunta_actual_id: Optional[UUID] = None
    completada: Optional[bool] = None

class ConversacionOut(ConversacionBase):
    id: UUID
    creado_en: datetime

    model_config = {"from_attributes": True}