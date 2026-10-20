from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.modules.transacciones import service
from app.modules.transacciones.model import TipoTransaccion
from app.modules.transacciones.schemas import TransaccionCrearEntrada, TransaccionListaSalida, TransaccionSalida
from app.modules.usuarios.model import Usuario

router = APIRouter(prefix="/transacciones", tags=["Transacciones"])


@router.post("", response_model=TransaccionSalida, status_code=status.HTTP_201_CREATED)
def crear_transaccion(
    datos: TransaccionCrearEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.crear_transaccion(db=db, usuario_id=usuario.id_usuario, datos=datos)
    except service.CuentaNoEncontradaError:
        raise HTTPException(status_code=404, detail="CUENTA_NO_ENCONTRADA")
    except service.ReglaTransaccionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.codigo)


@router.get("", response_model=TransaccionListaSalida)
def listar_transacciones(
    tipo_transaccion: TipoTransaccion | None = Query(default=None),
    cuenta_id: UUID | None = Query(default=None),
    limite: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        transacciones, total = service.listar_transacciones(
            db=db, usuario_id=usuario.id_usuario, tipo_transaccion=tipo_transaccion,
            cuenta_id=cuenta_id, limite=limite, offset=offset,
        )
        return {"transacciones": transacciones, "total": total, "limite": limite, "offset": offset}
    except service.CuentaNoEncontradaError:
        raise HTTPException(status_code=404, detail="CUENTA_NO_ENCONTRADA")


@router.get("/{id_transaccion}", response_model=TransaccionSalida)
def obtener_transaccion(
    id_transaccion: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.obtener_transaccion(db, usuario.id_usuario, id_transaccion)
    except service.TransaccionNoEncontradaError:
        raise HTTPException(status_code=404, detail="TRANSACCION_NO_ENCONTRADA")
