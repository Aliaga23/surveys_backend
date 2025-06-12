from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_admin_user  # Cambiamos la dependencia
from app.models.catalogos import (
    Rol, TipoPregunta, Canal,
    EstadoCampana, EstadoEntrega, EstadoDocumento,
    EstadoPago, MetodoPago
)
from app.schemas.catalogos import (
    RolCreate, RolOut, RolUpdate,
    TipoPreguntaCreate, TipoPreguntaOut, TipoPreguntaUpdate,
    CanalCreate, CanalOut, CanalUpdate,
    EstadoCampanaCreate, EstadoCampanaOut, EstadoCampanaUpdate,
    EstadoEntregaCreate, EstadoEntregaOut, EstadoEntregaUpdate,
    EstadoDocumentoCreate, EstadoDocumentoOut, EstadoDocumentoUpdate,
    EstadoPagoCreate, EstadoPagoOut, EstadoPagoUpdate,
    MetodoPagoCreate, MetodoPagoOut, MetodoPagoUpdate,
)

router = APIRouter(
  prefix="/catalogos",
  tags=["Catalogos"],
  dependencies=[Depends(get_admin_user)]  # Cambiado a get_admin_user para restringir acceso
)

def _generic_create(db: Session, Model, payload):
    if db.query(Model).filter(Model.nombre == payload.nombre).first():
        raise HTTPException(400, "Ya existe")
    obj = Model(**payload.dict())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def _generic_list(db: Session, Model, skip: int, limit: int):
    return db.query(Model).offset(skip).limit(limit).all()

def _generic_get(db: Session, Model, obj_id: int):
    obj = db.get(Model, obj_id)
    if not obj:
        raise HTTPException(404, "No encontrado")
    return obj

def _generic_update(db: Session, Model, obj_id: int, payload):
    obj = _generic_get(db, Model, obj_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

def _generic_delete(db: Session, Model, obj_id: int):
    obj = _generic_get(db, Model, obj_id)
    db.delete(obj); db.commit()

@router.post("/roles",     response_model=RolOut, status_code=201)
def create_rol(payload: RolCreate, db: Session = Depends(get_db)):
    return _generic_create(db, Rol, payload)

@router.get("/roles",      response_model=List[RolOut])
def list_roles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return _generic_list(db, Rol, skip, limit)

@router.get("/roles/{id}",  response_model=RolOut)
def get_rol(id: int, db: Session = Depends(get_db)):
    return _generic_get(db, Rol, id)

@router.put("/roles/{id}",  response_model=RolOut)
def update_rol(id: int, payload: RolUpdate, db: Session = Depends(get_db)):
    return _generic_update(db, Rol, id, payload)

@router.delete("/roles/{id}", status_code=204)
def delete_rol(id: int, db: Session = Depends(get_db)):
    _generic_delete(db, Rol, id)


@router.post("/tipos-pregunta", response_model=TipoPreguntaOut, status_code=201)
def create_tipo_pregunta(payload: TipoPreguntaCreate, db: Session = Depends(get_db)):
    return _generic_create(db, TipoPregunta, payload)

@router.get("/tipos-pregunta",  response_model=List[TipoPreguntaOut])
def list_tipos_pregunta(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return _generic_list(db, TipoPregunta, skip, limit)

@router.get("/tipos-pregunta/{id}", response_model=TipoPreguntaOut)
def get_tipo_pregunta(id: int, db: Session = Depends(get_db)):
    return _generic_get(db, TipoPregunta, id)

@router.put("/tipos-pregunta/{id}", response_model=TipoPreguntaOut)
def update_tipo_pregunta(id: int, payload: TipoPreguntaUpdate, db: Session = Depends(get_db)):
    return _generic_update(db, TipoPregunta, id, payload)

@router.delete("/tipos-pregunta/{id}", status_code=204)
def delete_tipo_pregunta(id: int, db: Session = Depends(get_db)):
    _generic_delete(db, TipoPregunta, id)


@router.post("/canales", response_model=CanalOut, status_code=201)
def create_canal(payload: CanalCreate, db: Session = Depends(get_db)):
    return _generic_create(db, Canal, payload)

@router.get("/canales",  response_model=List[CanalOut])
def list_canales(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return _generic_list(db, Canal, skip, limit)

@router.get("/canales/{id}", response_model=CanalOut)
def get_canal(id: int, db: Session = Depends(get_db)):
    return _generic_get(db, Canal, id)

@router.put("/canales/{id}", response_model=CanalOut)
def update_canal(id: int, payload: CanalUpdate, db: Session = Depends(get_db)):
    return _generic_update(db, Canal, id, payload)

@router.delete("/canales/{id}", status_code=204)
def delete_canal(id: int, db: Session = Depends(get_db)):
    _generic_delete(db, Canal, id)


@router.post("/estados-campana", response_model=EstadoCampanaOut, status_code=201)
def create_estado_campana(payload: EstadoCampanaCreate, db: Session = Depends(get_db)):
    return _generic_create(db, EstadoCampana, payload)

@router.get("/estados-campana",  response_model=List[EstadoCampanaOut])
def list_estados_campana(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return _generic_list(db, EstadoCampana, skip, limit)

@router.put("/estados-campana/{id}", response_model=EstadoCampanaOut)
def update_estado_campana(id: int, payload: EstadoCampanaUpdate, db: Session = Depends(get_db)):
    return _generic_update(db, EstadoCampana, id, payload)

@router.delete("/estados-campana/{id}", status_code=204)
def delete_estado_campana(id: int, db: Session = Depends(get_db)):
    _generic_delete(db, EstadoCampana, id)

@router.post("/estados-entrega", response_model=EstadoEntregaOut, status_code=201)
def create_estado_entrega(payload: EstadoEntregaCreate, db: Session = Depends(get_db)):
    return _generic_create(db, EstadoEntrega, payload)

@router.get("/estados-entrega", response_model=List[EstadoEntregaOut])
def list_estados_entrega(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return _generic_list(db, EstadoEntrega, skip, limit)

@router.put("/estados-entrega/{id}", response_model=EstadoEntregaOut)
def update_estado_entrega(id: int, payload: EstadoEntregaUpdate, db: Session = Depends(get_db)):
    return _generic_update(db, EstadoEntrega, id, payload)

@router.delete("/estados-entrega/{id}", status_code=204)
def delete_estado_entrega(id: int, db: Session = Depends(get_db)):
    _generic_delete(db, EstadoEntrega, id)

@router.post("/estados-documento", response_model=EstadoDocumentoOut, status_code=201)
def create_estado_documento(payload: EstadoDocumentoCreate, db: Session = Depends(get_db)):
    return _generic_create(db, EstadoDocumento, payload)

@router.get("/estados-documento", response_model=List[EstadoDocumentoOut])
def list_estados_documento(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return _generic_list(db, EstadoDocumento, skip, limit)

@router.put("/estados-documento/{id}", response_model=EstadoDocumentoOut)
def update_estado_documento(id: int, payload: EstadoDocumentoUpdate, db: Session = Depends(get_db)):
    return _generic_update(db, EstadoDocumento, id, payload)

@router.delete("/estados-documento/{id}", status_code=204)
def delete_estado_documento(id: int, db: Session = Depends(get_db)):
    _generic_delete(db, EstadoDocumento, id)


@router.post("/estados-pago", response_model=EstadoPagoOut, status_code=201)
def create_estado_pago(payload: EstadoPagoCreate, db: Session = Depends(get_db)):
    return _generic_create(db, EstadoPago, payload)

@router.get("/estados-pago",  response_model=List[EstadoPagoOut])
def list_estados_pago(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return _generic_list(db, EstadoPago, skip, limit)

@router.put("/estados-pago/{id}", response_model=EstadoPagoOut)
def update_estado_pago(id: int, payload: EstadoPagoUpdate, db: Session = Depends(get_db)):
    return _generic_update(db, EstadoPago, id, payload)

@router.delete("/estados-pago/{id}", status_code=204)
def delete_estado_pago(id: int, db: Session = Depends(get_db)):
    _generic_delete(db, EstadoPago, id)

@router.post("/metodos-pago", response_model=MetodoPagoOut, status_code=201)
def create_metodo_pago(payload: MetodoPagoCreate, db: Session = Depends(get_db)):
    return _generic_create(db, MetodoPago, payload)

@router.get("/metodos-pago",  response_model=List[MetodoPagoOut])
def list_metodos_pago(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return _generic_list(db, MetodoPago, skip, limit)

@router.put("/metodos-pago/{id}", response_model=MetodoPagoOut)
def update_metodo_pago(id: int, payload: MetodoPagoUpdate, db: Session = Depends(get_db)):
    return _generic_update(db, MetodoPago, id, payload)

@router.delete("/metodos-pago/{id}", status_code=204)
def delete_metodo_pago(id: int, db: Session = Depends(get_db)):
    _generic_delete(db, MetodoPago, id)
