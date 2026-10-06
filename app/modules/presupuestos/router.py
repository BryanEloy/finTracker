from typing import Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db

from app.modules.presupuestos import service
from app.modules.presupuestos.model import EstadoPresupuesto
from app.modules.presupuestos.schemas import (
    PresupuestoCrearEntrada,
    PresupuestoCierreEntrada,
    PresupuestoDetalle,
    PresupuestoGastosSalida,
    PresupuestoListaSalida,
)


router = APIRouter(
    prefix="/presupuestos",
    tags=["Presupuestos"],
)


# ============================================================
# EP-PRE-01
# CREAR PRESUPUESTO
# POST /api/v1/presupuestos
# ============================================================

@router.post(
    "",
    response_model=PresupuestoDetalle,
    status_code=status.HTTP_201_CREATED,
)
def crear_presupuesto(
    datos: PresupuestoCrearEntrada,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    try:
        return service.crear_presupuesto(
            db=db,
            usuario_id=usuario.id_usuario,
            datos=datos,
        )

    except service.CategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CATEGORIA_NO_ENCONTRADA",
        )

    except service.CategoriaInactivaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CATEGORIA_INACTIVA",
        )

    except service.PresupuestoActivoExistenteError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PRESUPUESTO_ACTIVO_EXISTENTE",
        )

    except service.DistribucionInvalidaError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DISTRIBUCION_INVALIDA",
        )

    except service.DistribucionNoRepresentableError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DISTRIBUCION_NO_REPRESENTABLE",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DATOS_INVALIDOS",
        )


# ============================================================
# EP-PRE-02
# LISTAR PRESUPUESTOS
# GET /api/v1/presupuestos
# ============================================================

@router.get(
    "",
    response_model=PresupuestoListaSalida,
    status_code=status.HTTP_200_OK,
)
def listar_presupuestos(
    estado: Literal[
        "ACTIVO",
        "FINALIZADO",
        "CANCELADO",
        "TODOS",
    ] = Query(
        default="ACTIVO",
    ),

    limite: int = Query(
        default=20,
        ge=1,
        le=100,
    ),

    offset: int = Query(
        default=0,
        ge=0,
    ),

    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    estado_db = (
        None
        if estado == "TODOS"
        else EstadoPresupuesto(estado)
    )

    presupuestos, total = (
        service.listar_presupuestos(
            db=db,
            usuario_id=usuario.id_usuario,
            estado=estado_db,
            limite=limite,
            offset=offset,
        )
    )

    return {
        "presupuestos": presupuestos,
        "total": total,
        "limite": limite,
        "offset": offset,
    }


# ============================================================
# EP-PRE-03
# OBTENER DETALLE
# GET /api/v1/presupuestos/{id_presupuesto}
# ============================================================

@router.get(
    "/{id_presupuesto}",
    response_model=PresupuestoDetalle,
    status_code=status.HTTP_200_OK,
)
def obtener_presupuesto(
    id_presupuesto: UUID,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    try:
        return service.obtener_detalle_presupuesto(
            db=db,
            usuario_id=usuario.id_usuario,
            id_presupuesto=id_presupuesto,
        )

    except service.PresupuestoNoEncontradoError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PRESUPUESTO_NO_ENCONTRADO",
        )


# ============================================================
# EP-PRE-04
# CERRAR PRESUPUESTO
# POST /api/v1/presupuestos/{id_presupuesto}/cierre
# ============================================================

@router.post(
    "/{id_presupuesto}/cierre",
    response_model=PresupuestoDetalle,
    status_code=status.HTTP_200_OK,
)
def cerrar_presupuesto(
    id_presupuesto: UUID,
    datos: PresupuestoCierreEntrada,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    try:
        return service.cerrar_presupuesto(
            db=db,
            usuario_id=usuario.id_usuario,
            id_presupuesto=id_presupuesto,
            accion=datos.accion,
        )

    except service.PresupuestoNoEncontradoError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PRESUPUESTO_NO_ENCONTRADO",
        )

    except service.PresupuestoNoFinalizableError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PRESUPUESTO_NO_FINALIZABLE",
        )

    except service.PresupuestoCerradoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PRESUPUESTO_CERRADO",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DATOS_INVALIDOS",
        )


# ============================================================
# EP-PRE-05
# LISTAR GASTOS DEL PRESUPUESTO
# GET /api/v1/presupuestos/{id_presupuesto}/gastos
# ============================================================

@router.get(
    "/{id_presupuesto}/gastos",
    response_model=PresupuestoGastosSalida,
    status_code=status.HTTP_200_OK,
)
def listar_gastos_presupuesto(
    id_presupuesto: UUID,

    alcance: Literal[
        "TODOS",
        "PRESUPUESTADOS",
        "NO_PRESUPUESTADOS",
    ] = Query(
        default="TODOS",
    ),

    categoria_id: UUID | None = Query(
        default=None,
    ),

    limite: int = Query(
        default=20,
        ge=1,
        le=100,
    ),

    offset: int = Query(
        default=0,
        ge=0,
    ),

    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    try:
        gastos, total = service.listar_gastos(
            db=db,
            usuario_id=usuario.id_usuario,
            id_presupuesto=id_presupuesto,
            alcance=alcance,
            categoria_id=categoria_id,
            limite=limite,
            offset=offset,
        )

        return {
            "gastos": gastos,
            "total": total,
            "limite": limite,
            "offset": offset,
        }

    except service.PresupuestoNoEncontradoError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PRESUPUESTO_NO_ENCONTRADO",
        )

    except service.CategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CATEGORIA_NO_ENCONTRADA",
        )