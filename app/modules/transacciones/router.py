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
from app.modules.transacciones import service
from app.modules.transacciones.model import TipoTransaccion
from app.modules.transacciones.schemas import (
    TransaccionCrearEntrada,
    TransaccionListaSalida,
    TransaccionSalida,
)
from app.modules.usuarios.model import Usuario


router = APIRouter(
    prefix="/transacciones",
    tags=["Transacciones"],
)


# ============================================================
# POST /transacciones
# ============================================================

@router.post(
    "",
    response_model=TransaccionSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_transaccion(
    datos: TransaccionCrearEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.crear_transaccion(
            db=db,
            usuario_id=usuario.id_usuario,
            tipo_transaccion=datos.tipo_transaccion,
            cuenta_id=datos.cuenta_id,
            cuenta_destino_id=datos.cuenta_destino_id,
            categoria_id=datos.categoria_id,
            subcategoria_id=datos.subcategoria_id,
            monto_transaccion=datos.monto_transaccion,
            comentario_transaccion=datos.comentario_transaccion,
        )

    except service.CuentaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CUENTA_NO_ENCONTRADA",
        )

    except service.CategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CATEGORIA_NO_ENCONTRADA",
        )

    except service.SubcategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SUBCATEGORIA_NO_ENCONTRADA",
        )

    except service.CuentaInactivaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CUENTA_INACTIVA",
        )

    except service.CategoriaInactivaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CATEGORIA_INACTIVA",
        )

    except service.SubcategoriaInactivaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SUBCATEGORIA_INACTIVA",
        )

    except service.SaldoInsuficienteError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SALDO_INSUFICIENTE",
        )

    except service.LimiteCreditoExcedidoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="LIMITE_CREDITO_EXCEDIDO",
        )

    except service.PagoSuperaDeudaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PAGO_SUPERA_DEUDA",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DATOS_INVALIDOS",
        )


# ============================================================
# GET /transacciones
# ============================================================

@router.get(
    "",
    response_model=TransaccionListaSalida,
)
def listar_transacciones(
    tipo_transaccion: TipoTransaccion | None = Query(
        default=None
    ),
    cuenta_id: UUID | None = Query(
        default=None
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
    usuario: Usuario = Depends(get_current_user),
):
    try:
        transacciones, total = (
            service.listar_transacciones(
                db=db,
                usuario_id=usuario.id_usuario,
                tipo_transaccion=tipo_transaccion,
                cuenta_id=cuenta_id,
                limite=limite,
                offset=offset,
            )
        )

        return {
            "transacciones": transacciones,
            "total": total,
            "limite": limite,
            "offset": offset,
        }

    except service.CuentaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CUENTA_NO_ENCONTRADA",
        )


# ============================================================
# GET /transacciones/{id_transaccion}
# ============================================================

@router.get(
    "/{id_transaccion}",
    response_model=TransaccionSalida,
)
def obtener_transaccion(
    id_transaccion: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.obtener_transaccion(
            db=db,
            usuario_id=usuario.id_usuario,
            id_transaccion=id_transaccion,
        )

    except service.TransaccionNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TRANSACCION_NO_ENCONTRADA",
        )