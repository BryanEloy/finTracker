from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.modules.usuarios.model import Usuario
from app.modules.presupuestos import service
from app.modules.presupuestos.schemas import (
    PresupuestoCrearEntrada, PresupuestoActualizarEntrada, GrupoDistribucionEntrada,
)

router=APIRouter(tags=["Presupuestos V1.1"])

def manejar(error):
    raise HTTPException(status_code=error.codigo,detail=error.mensaje) from error

@router.get("/presupuestos")
def listar(db:Session=Depends(get_db),usuario:Usuario=Depends(get_current_user)):
    return service.listar(db,usuario.id_usuario)

@router.get("/presupuestos/{id_periodo}")
def obtener(id_periodo:UUID,db:Session=Depends(get_db),usuario:Usuario=Depends(get_current_user)):
    try: return service.detalle(db,usuario.id_usuario,id_periodo)
    except service.PresupuestoError as exc: manejar(exc)

@router.post("/presupuestos",status_code=status.HTTP_201_CREATED)
def crear(datos:PresupuestoCrearEntrada,db:Session=Depends(get_db),usuario:Usuario=Depends(get_current_user)):
    try: return service.crear(db,usuario.id_usuario,datos)
    except service.PresupuestoError as exc: manejar(exc)

@router.patch("/presupuestos/{id_periodo}")
def editar(id_periodo:UUID,datos:PresupuestoActualizarEntrada,db:Session=Depends(get_db),usuario:Usuario=Depends(get_current_user)):
    try: return service.editar(db,usuario.id_usuario,id_periodo,datos)
    except service.PresupuestoError as exc: manejar(exc)

@router.put("/presupuestos/{id_periodo}/distribucion")
def distribuir(id_periodo:UUID,grupos:list[GrupoDistribucionEntrada],db:Session=Depends(get_db),usuario:Usuario=Depends(get_current_user)):
    try: return service.distribuir(db,usuario.id_usuario,id_periodo,grupos)
    except service.PresupuestoError as exc: manejar(exc)

@router.post("/presupuestos/{id_periodo}/finalizar")
def finalizar(id_periodo:UUID,db:Session=Depends(get_db),usuario:Usuario=Depends(get_current_user)):
    try: return service.cerrar(db,usuario.id_usuario,id_periodo,"FINALIZADO")
    except service.PresupuestoError as exc: manejar(exc)

@router.post("/presupuestos/{id_periodo}/cancelar")
def cancelar(id_periodo:UUID,db:Session=Depends(get_db),usuario:Usuario=Depends(get_current_user)):
    try: return service.cerrar(db,usuario.id_usuario,id_periodo,"CANCELADO")
    except service.PresupuestoError as exc: manejar(exc)
