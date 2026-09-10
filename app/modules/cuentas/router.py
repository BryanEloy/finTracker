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
from app.modules.cuentas.schemas import (
    CuentaActualizarEntrada,
    CuentaCrearEntrada,
    CuentaEstadoEntrada,
    CuentaEstadoSalida,
    CuentaListaSalida,
    CuentaPublica,
    EstadoCuenta,
    OperacionCuenta,
)
from app.modules.cuentas.service import (
    CuentaNoEncontradaError,
    DatosCuentaInvalidosError,
    LimiteCreditoInvalidoError,
    NombreCuentaDuplicadoError,
    actualizar_cuenta,
    cambiar_estado_cuenta,
    listar_cuentas,
    obtener_cuenta,
    registrar_cuenta,
)
from app.modules.usuarios.model import Usuario


router = APIRouter(
    prefix="/cuentas",
    tags=["Cuentas"],
)


@router.post(
    "",
    response_model=CuentaPublica,
    status_code=status.HTTP_201_CREATED,
)
def crear_cuenta(
    datos: CuentaCrearEntrada,
    usuario: Usuario = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    try:
        return registrar_cuenta(
            db,
            usuario,
            datos,
        )

    except NombreCuentaDuplicadoError:
        raise HTTPException(
            status_code=409,
            detail="NOMBRE_CUENTA_DUPLICADO",
        )

    except (
        DatosCuentaInvalidosError,
        LimiteCreditoInvalidoError,
    ):
        raise HTTPException(
            status_code=422,
            detail="DATOS_CUENTA_INVALIDOS",
        )


@router.get(
    "",
    response_model=CuentaListaSalida,
)
def obtener_cuentas(
    estado: EstadoCuenta = Query(
        default=EstadoCuenta.ACTIVA
    ),
    operacion: OperacionCuenta | None = Query(
        default=None
    ),
    usuario: Usuario = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return listar_cuentas(
        db,
        usuario,
        estado,
        operacion,
    )


@router.get(
    "/{id_cuenta}",
    response_model=CuentaPublica,
)
def obtener_detalle_cuenta(
    id_cuenta: UUID,
    usuario: Usuario = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    try:
        return obtener_cuenta(
            db,
            usuario,
            id_cuenta,
        )

    except CuentaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="CUENTA_NO_ENCONTRADA",
        )


@router.patch(
    "/{id_cuenta}",
    response_model=CuentaPublica,
)
def modificar_cuenta(
    id_cuenta: UUID,
    datos: CuentaActualizarEntrada,
    usuario: Usuario = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    try:
        return actualizar_cuenta(
            db,
            usuario,
            id_cuenta,
            datos,
        )

    except CuentaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="CUENTA_NO_ENCONTRADA",
        )

    except NombreCuentaDuplicadoError:
        raise HTTPException(
            status_code=409,
            detail="NOMBRE_CUENTA_DUPLICADO",
        )

    except LimiteCreditoInvalidoError:
        raise HTTPException(
            status_code=409,
            detail="LIMITE_MENOR_AL_CREDITO_UTILIZADO",
        )

    except DatosCuentaInvalidosError:
        raise HTTPException(
            status_code=422,
            detail="DATOS_CUENTA_INVALIDOS",
        )


@router.patch(
    "/{id_cuenta}/estado",
    response_model=CuentaEstadoSalida,
)
def modificar_estado_cuenta(
    id_cuenta: UUID,
    datos: CuentaEstadoEntrada,
    usuario: Usuario = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    try:
        return cambiar_estado_cuenta(
            db,
            usuario,
            id_cuenta,
            datos.es_activa_cuenta,
        )

    except CuentaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="CUENTA_NO_ENCONTRADA",
        )