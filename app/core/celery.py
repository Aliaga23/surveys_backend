from celery import Celery
from app.core.config import settings
import os
from dotenv import load_dotenv

load_dotenv()

celery = Celery(
    'app',
    broker=os.getenv('REDIS_URL'),
    backend=os.getenv('REDIS_URL')
)

@celery.task
async def send_email_task(email_data: dict) -> bool:
    from app.services.email_service import enviar_email
    return await enviar_email(
        destinatario_email=email_data["destinatario_email"],
        destinatario_nombre=email_data["destinatario_nombre"],
        asunto=email_data["asunto"],
        nombre_campana=email_data["nombre_campana"],
        nombre_empresa=email_data["nombre_empresa"],
        url_encuesta=email_data["url_encuesta"]
    )