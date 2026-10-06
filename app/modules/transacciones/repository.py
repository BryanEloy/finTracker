from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.cuentas.model import Cuenta
from app.modules.categorias.model import Categoria, Subcategoria
from app.modules.transacciones.model import (
    TipoTransaccion,
    Transaccion,
)

from app.modules.usuarios.model import Usuario


# ============================================================
# CUENTAS
# ============================================================

def bloquear_cuentas(
    db: Session,
    usuario_id: UUID,
    ids_cuentas: list[UUID],
) -> dict[UUID, Cuenta]:
    """
    Bloquea las cuentas participantes mediante SELECT FOR UPDATE.

    Las bloquea siempre en orden por UUID para mantener un orden
    consistente cuando una transferencia utiliza dos cuentas.
    """

    ids_unicos = list(set(ids_cuentas))

    stmt = (
        select(Cuenta)
        .where(
            Cuenta.usuario_id == usuario_id,
            Cuenta.id_cuenta.in_(ids_unicos),
        )
        .order_by(Cuenta.id_cuenta)
        .with_for_update()
    )

    cuentas = list(db.scalars(stmt).all())

    return {
        cuenta.id_cuenta: cuenta
        for cuenta in cuentas
    }


def obtener_cuenta_propia(
    db: Session,
    usuario_id: UUID,
    id_cuenta: UUID,
) -> Cuenta | None:
    """
    Consulta una cuenta propia sin bloquearla.

    Se utilizará principalmente para filtros de historial.
    """

    stmt = select(Cuenta).where(
        Cuenta.id_cuenta == id_cuenta,
        Cuenta.usuario_id == usuario_id,
    )

    return db.scalar(stmt)


# ============================================================
# CATEGORÍA / SUBCATEGORÍA
# ============================================================

def obtener_categoria_propia(
    db: Session,
    usuario_id: UUID,
    id_categoria: UUID,
) -> Categoria | None:

    stmt = select(Categoria).where(
        Categoria.id_categoria == id_categoria,
        Categoria.usuario_id == usuario_id,
    )

    return db.scalar(stmt)


def obtener_subcategoria_propia(
    db: Session,
    usuario_id: UUID,
    id_subcategoria: UUID,
) -> Subcategoria | None:

    stmt = (
        select(Subcategoria)
        .join(
            Categoria,
            Categoria.id_categoria
            == Subcategoria.categoria_id,
        )
        .where(
            Subcategoria.id_subcategoria
            == id_subcategoria,
            Categoria.usuario_id == usuario_id,
        )
    )

    return db.scalar(stmt)


# ============================================================
# CÁLCULO DE CUENTAS NO CREDITICIAS
# ============================================================

def calcular_movimientos_cuenta_no_crediticia(
    db: Session,
    usuario_id: UUID,
    id_cuenta: UUID,
) -> Decimal:
    """
    Devuelve el efecto neto de las transacciones sobre una cuenta
    EFECTIVO, DEBITO o AHORRO.

    INGRESO en cuenta principal           -> +
    GASTO en cuenta principal             -> -
    TRANSFERENCIA como origen             -> -
    TRANSFERENCIA como destino            -> +
    """

    ingresos = func.coalesce(
        func.sum(
            Transaccion.monto_transaccion
        ).filter(
            Transaccion.tipo_transaccion
            == TipoTransaccion.INGRESO,
            Transaccion.cuenta_id == id_cuenta,
        ),
        0,
    )

    gastos = func.coalesce(
        func.sum(
            Transaccion.monto_transaccion
        ).filter(
            Transaccion.tipo_transaccion
            == TipoTransaccion.GASTO,
            Transaccion.cuenta_id == id_cuenta,
        ),
        0,
    )

    transferencias_salientes = func.coalesce(
        func.sum(
            Transaccion.monto_transaccion
        ).filter(
            Transaccion.tipo_transaccion
            == TipoTransaccion.TRANSFERENCIA,
            Transaccion.cuenta_id == id_cuenta,
        ),
        0,
    )

    transferencias_entrantes = func.coalesce(
        func.sum(
            Transaccion.monto_transaccion
        ).filter(
            Transaccion.tipo_transaccion
            == TipoTransaccion.TRANSFERENCIA,
            Transaccion.cuenta_destino_id == id_cuenta,
        ),
        0,
    )

    stmt = select(
        ingresos
        - gastos
        - transferencias_salientes
        + transferencias_entrantes
    ).where(
        Transaccion.usuario_id == usuario_id
    )

    resultado = db.scalar(stmt)

    return Decimal(resultado or 0)


def calcular_saldo_actual(
    db: Session,
    cuenta: Cuenta,
) -> Decimal:

    movimientos = calcular_movimientos_cuenta_no_crediticia(
        db=db,
        usuario_id=cuenta.usuario_id,
        id_cuenta=cuenta.id_cuenta,
    )

    return (
        Decimal(cuenta.saldo_inicial_cuenta)
        + movimientos
    )


# ============================================================
# CÁLCULO DE CRÉDITO
# ============================================================

def calcular_credito_utilizado(
    db: Session,
    cuenta: Cuenta,
) -> Decimal:
    """
    Para CREDITO:

    saldo_inicial_cuenta = deuda existente al crear la cuenta.

    GASTOS realizados con la cuenta de crédito aumentan deuda.

    TRANSFERENCIAS recibidas por la cuenta de crédito
    representan pagos y disminuyen deuda.
    """

    gastos = func.coalesce(
        func.sum(Transaccion.monto_transaccion).filter(
            Transaccion.tipo_transaccion
            == TipoTransaccion.GASTO,
            Transaccion.cuenta_id == cuenta.id_cuenta,
        ),
        0,
    )

    pagos = func.coalesce(
        func.sum(Transaccion.monto_transaccion).filter(
            Transaccion.tipo_transaccion
            == TipoTransaccion.TRANSFERENCIA,
            Transaccion.cuenta_destino_id
            == cuenta.id_cuenta,
        ),
        0,
    )

    stmt = select(
        gastos - pagos
    ).where(
        Transaccion.usuario_id == cuenta.usuario_id
    )

    movimientos = db.scalar(stmt)

    return (
        Decimal(cuenta.saldo_inicial_cuenta)
        + Decimal(movimientos or 0)
    )


# ============================================================
# CREAR TRANSACCIÓN
# ============================================================

def agregar_transaccion(
    db: Session,
    transaccion: Transaccion,
) -> None:
    """
    Agrega la transacción a la sesión.

    IMPORTANTE:
    NO hace commit.
    El commit pertenece al service para conservar atomicidad.
    """

    db.add(transaccion)
    db.flush()


# ============================================================
# CONSULTAR TRANSACCIÓN
# ============================================================

def obtener_transaccion_por_id(
    db: Session,
    usuario_id: UUID,
    id_transaccion: UUID,
) -> Transaccion | None:

    stmt = select(Transaccion).where(
        Transaccion.id_transaccion == id_transaccion,
        Transaccion.usuario_id == usuario_id,
    )

    return db.scalar(stmt)


# ============================================================
# LISTAR TRANSACCIONES
# ============================================================

def listar_transacciones(
    db: Session,
    usuario_id: UUID,
    tipo_transaccion: TipoTransaccion | None,
    cuenta_id: UUID | None,
    limite: int,
    offset: int,
) -> tuple[list[Transaccion], int]:

    filtros = [
        Transaccion.usuario_id == usuario_id
    ]

    if tipo_transaccion is not None:
        filtros.append(
            Transaccion.tipo_transaccion
            == tipo_transaccion
        )

    if cuenta_id is not None:
        filtros.append(
            or_(
                Transaccion.cuenta_id == cuenta_id,
                Transaccion.cuenta_destino_id == cuenta_id,
            )
        )

    # ----------------------------------------
    # TOTAL ANTES DE PAGINAR
    # ----------------------------------------

    stmt_total = (
        select(func.count())
        .select_from(Transaccion)
        .where(*filtros)
    )

    total = db.scalar(stmt_total) or 0

    # ----------------------------------------
    # ELEMENTOS
    # ----------------------------------------

    stmt = (
        select(Transaccion)
        .where(*filtros)
        .order_by(
            Transaccion.fecha_registro_transaccion.desc(),
            Transaccion.id_transaccion.desc(),
        )
        .limit(limite)
        .offset(offset)
    )

    transacciones = list(
        db.scalars(stmt).all()
    )

    return transacciones, total

def bloquear_usuario(
    db: Session,
    usuario_id: UUID,
):
    stmt = (
        select(Usuario)
        .where(
            Usuario.id_usuario == usuario_id
        )
        .with_for_update()
    )

    return db.scalar(stmt)