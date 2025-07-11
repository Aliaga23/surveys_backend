from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base
from app.routers import auth, catalogos, subscription, plantillas_router, campanas_router, preguntas_router
from app.routers import opciones_router, entregas_router, destinatarios_router
from app.routers.respuestas_router import public_router as respuestas_public_router
from app.routers.respuestas_router import private_router as respuestas_private_router
from app.routers.entregas_router import public_router as entregas_public_router
from app.routers import whatsapp_router
from app.routers import vapi_router
from app.routers import analytics_router
#from app.routers import nlp_router
from app.routers import encuestas_router
from app.routers import seeder_router
from app.routers import pdf_router
from app.routers import dashboard_router
from app.routers import chat_router

app = FastAPI(title="Mi API SaaS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)


Base.metadata.create_all(bind=engine)

# Registrar todos los routers
app.include_router(auth.router)
app.include_router(catalogos.router)
app.include_router(subscription.router)
app.include_router(plantillas_router.router)
app.include_router(campanas_router.router)
app.include_router(preguntas_router.router)
app.include_router(opciones_router.router)
app.include_router(entregas_router.router)
app.include_router(destinatarios_router.router)
app.include_router(respuestas_public_router)
app.include_router(respuestas_private_router)
app.include_router(entregas_public_router)
app.include_router(whatsapp_router.router)
app.include_router(vapi_router.router)
app.include_router(analytics_router.router)
#app.include_router(nlp_router.router)
app.include_router(encuestas_router.router)
app.include_router(pdf_router.router)
app.include_router(seeder_router.router)
app.include_router(dashboard_router.router)
app.include_router(chat_router.router)

@app.get("/", summary="Health check")
async def health_check():
    return {"status": "ok", "message": "API running"}
