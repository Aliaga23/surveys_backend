web: uvicorn app.main:app --host 0.0.0.0 --port 8000
worker: celery -A app.core.celery.celery worker --loglevel=info --pool=solo
