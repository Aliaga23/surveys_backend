from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging

from app.core.database import get_db
from app.core.security import get_admin_user, TokenData
from app.services.seeder_service import DatabaseSeeder

router = APIRouter(
    prefix="/seeder",
    tags=["Seeder"],
)

@router.post("/run", 
    summary="Ejecutar Database Seeder",
    description="Pobla la base de datos con datos de prueba: 30 suscriptores, 4 operadores por suscriptor, 5 plantillas por suscriptor, y ~300 entregas con respuestas realistas",
    response_model=Dict[str, Any])
async def run_seeder(
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_admin_user)
):
    """
    Ejecuta el seeder de la base de datos.
    
    Este endpoint crea:
    - 30 suscriptores (empresas)
    - 120 operadores (4 por suscriptor)
    - 150 plantillas (5 por suscriptor)
    - 600 destinatarios (20 por suscriptor)
    - ~300 campañas
    - ~300 entregas con respuestas realistas
    
    Solo puede ser ejecutado por administradores.
    """
    try:
        seeder = DatabaseSeeder(db)
        result = seeder.run()
        
        return {
            "success": True,
            "message": "Seeding completado exitosamente",
            "data": result
        }
        
    except Exception as e:
        logging.error(f"Error durante el seeding: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante el seeding: {str(e)}"
        )

@router.post("/init",
    summary="Inicializar sistema con roles y usuarios base",
    description="Crea los roles admin/empresa/operator, un administrador y un suscriptor demo.",
    response_model=Dict[str, Any],
    dependencies=[]  # ← sin token para poder usarlo la primera vez
)
async def init_seed(db: Session = Depends(get_db)):
    """
    Inicializa la base de datos con los datos mínimos:
    - Roles (admin, empresa, operator)
    - Usuario administrador
    - Suscriptor de prueba
    """
    try:
        seeder = DatabaseSeeder(db)
        result = seeder.seed_basico()
        return {
            "success": True,
            "message": "Inicialización básica completada",
            "data": result
        }
    except Exception as e:
        logging.error(f"Error durante init seeder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante inicialización: {str(e)}"
        )

@router.get("/status",
    summary="Estado del Seeder",
    description="Verifica si el seeder ya ha sido ejecutado revisando la cantidad de datos existentes",
    response_model=Dict[str, Any])
async def get_seeder_status(
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_admin_user)
):
    """
    Obtiene el estado actual de la base de datos para verificar si el seeder ya fue ejecutado.
    """
    try:
        from app.models.suscriptor import Suscriptor
        from app.models.cuenta_usuario import CuentaUsuario
        from app.models.survey import PlantillaEncuesta, EntregaEncuesta
        
        # Contar registros existentes
        suscriptores_count = db.query(Suscriptor).count()
        operadores_count = db.query(CuentaUsuario).filter(CuentaUsuario.rol_id == 3).count()
        plantillas_count = db.query(PlantillaEncuesta).count()
        entregas_count = db.query(EntregaEncuesta).count()
        
        return {
            "suscriptores": suscriptores_count,
            "operadores": operadores_count,
            "plantillas": plantillas_count,
            "entregas": entregas_count,
            "seeder_ejecutado": suscriptores_count >= 30 and operadores_count >= 120
        }
        
    except Exception as e:
        logging.error(f"Error obteniendo estado del seeder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo estado: {str(e)}"
        )

@router.delete("/clear",
    summary="Limpiar Datos de Prueba",
    description="Elimina todos los datos de prueba creados por el seeder (SOLO PARA DESARROLLO)",
    response_model=Dict[str, Any])
async def clear_test_data(
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_admin_user)
):
    """
    Elimina todos los datos de prueba creados por el seeder.
    ⚠️ ADVERTENCIA: Esta operación elimina todos los datos de prueba.
    Solo usar en desarrollo.
    """
    try:
        from app.models.survey import (
            RespuestaPregunta, RespuestaEncuesta, EntregaEncuesta,
            CampanaEncuesta, PreguntaEncuesta, OpcionEncuesta, PlantillaEncuesta, Destinatario
        )
        from app.models.cuenta_usuario import CuentaUsuario
        from app.models.suscriptor import Suscriptor
        
        # Eliminar en orden para respetar las foreign keys
        db.query(RespuestaPregunta).delete()
        db.query(RespuestaEncuesta).delete()
        db.query(EntregaEncuesta).delete()
        db.query(CampanaEncuesta).delete()
        db.query(PreguntaEncuesta).delete()
        db.query(OpcionEncuesta).delete()
        db.query(PlantillaEncuesta).delete()
        db.query(Destinatario).delete()
        db.query(CuentaUsuario).filter(CuentaUsuario.rol_id == 3).delete()  # Solo operadores
        db.query(Suscriptor).delete()
        
        db.commit()
        
        return {
            "success": True,
            "message": "Datos de prueba eliminados exitosamente"
        }
        
    except Exception as e:
        db.rollback()
        logging.error(f"Error eliminando datos de prueba: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error eliminando datos: {str(e)}"
        ) 