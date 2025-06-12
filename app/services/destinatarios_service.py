from typing import List, Optional, Dict
import pandas as pd
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.models.survey import Destinatario
from app.schemas.destinatarios_schema import DestinarioCreate, DestinarioUpdate

def create_destinatario(
    db: Session, 
    suscriptor_id: UUID, 
    payload: DestinarioCreate
) -> Destinatario:
    destinatario = Destinatario(**payload.model_dump(), suscriptor_id=suscriptor_id)
    db.add(destinatario)
    db.commit()
    db.refresh(destinatario)
    return destinatario

def get_destinatario(db: Session, destinatario_id: UUID) -> Optional[Destinatario]:
    return db.query(Destinatario).filter(Destinatario.id == destinatario_id).first()

def list_destinatarios(
    db: Session, 
    suscriptor_id: UUID,
    skip: int = 0,
    limit: int = 100
) -> List[Destinatario]:
    return (
        db.query(Destinatario)
        .filter(Destinatario.suscriptor_id == suscriptor_id)
        .offset(skip)
        .limit(limit)
        .all()
    )

def update_destinatario(
    db: Session, 
    destinatario_id: UUID, 
    payload: DestinarioUpdate
) -> Optional[Destinatario]:
    destinatario = get_destinatario(db, destinatario_id)
    if not destinatario:
        return None
    
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(destinatario, field, value)
    
    db.commit()
    db.refresh(destinatario)
    return destinatario

def delete_destinatario(db: Session, destinatario_id: UUID) -> bool:
    destinatario = get_destinatario(db, destinatario_id)
    if not destinatario:
        return False
    db.delete(destinatario)
    db.commit()
    return True

async def process_excel_destinatarios(
    db: Session,
    file: UploadFile,
    suscriptor_id: UUID
) -> Dict[str, int]:
    """
    Procesa un archivo Excel con destinatarios y los crea en la base de datos.
    Retorna estadísticas del proceso.
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser un Excel (.xlsx o .xls)"
        )

    try:
        # Leer el Excel
        df = pd.read_excel(file.file)
        
        # Validar columnas requeridas
        required_columns = {'nombre', 'email', 'telefono'}
        if not required_columns.issubset(df.columns):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El Excel debe contener las columnas: {required_columns}"
            )

        # Inicializar contadores
        total = 0
        creados = 0
        duplicados = 0
        errores = 0

        # Procesar cada fila
        for _, row in df.iterrows():
            total += 1
            try:
                # Verificar si ya existe por email o teléfono
                existing = (
                    db.query(Destinatario)
                    .filter(
                        Destinatario.suscriptor_id == suscriptor_id,
                        (
                            (Destinatario.email == row['email']) |
                            (Destinatario.telefono == str(row['telefono']))
                        )
                    )
                    .first()
                )

                if existing:
                    duplicados += 1
                    continue

                # Crear nuevo destinatario
                destinatario = Destinatario(
                    suscriptor_id=suscriptor_id,
                    nombre=row['nombre'],
                    email=row['email'] if pd.notna(row['email']) else None,
                    telefono=str(row['telefono']) if pd.notna(row['telefono']) else None
                )
                db.add(destinatario)
                creados += 1

            except Exception as e:
                errores += 1
                continue

        # Commit al final para mejor rendimiento
        db.commit()

        return {
            "total_procesados": total,
            "creados": creados,
            "duplicados": duplicados,
            "errores": errores
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error procesando el archivo: {str(e)}"
        )
    finally:
        file.file.close()