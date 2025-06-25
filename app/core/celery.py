from celery import Celery

# Redis URL directa (Railway)
REDIS_URL = "redis://default:uMbFovROqGlZCxvIyhzvcKpTscGCqAyI@shuttle.proxy.rlwy.net:48663"

celery = Celery(
    'app',
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Ejemplo de tarea
@celery.task
def send_email_task(email_data: dict) -> bool:
    import asyncio
    from app.services.email_service import enviar_email
    return asyncio.run(enviar_email(**email_data))
