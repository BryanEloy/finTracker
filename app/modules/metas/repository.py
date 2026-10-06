from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.cuentas.model import Cuenta
from app.modules.metas.model import (
    AsignacionMeta,
    EstadoMeta,
    Meta,
    TipoAsignacion,
)
from app.modules.transacciones.repository import (
    calcular_credito_utilizado,
    calcular_saldo_actual,
)
from app.modules.usuarios.model import Usuario


# ============================================================
# BLOQUEOS
# ============================================================

def bloquear_usuario(
    db: Session,
    usuario_id: UUID,
):
    stmt = (
        select(Usuario)
        .where(Usuario.id_usuario == usuario_id)
        .with_for_update()
    )

    return db.scalar(stmt)


def bloquear_cuenta(
    db: Session,
    usuario_id: UUID,
    cuenta_id: UUID,
):
    stmt = (
        select(Cuenta)
        .where(
            Cuenta.id_cuenta == cuenta_id,
            Cuenta.usuario_id == usuario_id,
        )
        .with_for_update()
    )

    return db.scalar(stmt)


def bloquear_meta(
    db: Session,
    usuario_id: UUID,
    id_meta: UUID,
):
    stmt = (
        select(Meta)
        .where(
            Meta.id_meta == id_meta,
            Meta.usuario_id == usuario_id,
        )
        .with_for_update()
    )

    return db.scalar(stmt)


# ============================================================
# CONSULTAS DE META
# ============================================================

def obtener_meta_por_id(
    db: Session,
    usuario_id: UUID,
    id_meta: UUID,
):
    stmt = select(Meta).where(
        Meta.id_meta == id_meta,
        Meta.usuario_id == usuario_id,
    )

    return db.scalar(stmt)

def existe_nombre_meta(
    db: Session,
    usuario_id: UUID,
    cuenta_id: UUID,
    nombre_meta: str,
    excluir_id_meta: UUID | None = None,
) -> bool:

    stmt = select(Meta.id_meta).where(
        Meta.usuario_id == usuario_id,
        Meta.cuenta_id == cuenta_id,
        func.lower(Meta.nombre_meta)
        == nombre_meta.lower(),
    )

    if excluir_id_meta is not None:
        stmt = stmt.where(
            Meta.id_meta != excluir_id_meta
        )

    return db.scalar(stmt) is not None


def agregar_meta(
    db: Session,
    meta: Meta,
):
    db.add(meta)
    db.flush()

# ============================================================
# CONSULTAS DE CUENTA
# ============================================================

def obtener_cuenta_propia(
    db: Session,
    usuario_id: UUID,
    cuenta_id: UUID,
):
    stmt = select(Cuenta).where(
        Cuenta.id_cuenta == cuenta_id,
        Cuenta.usuario_id == usuario_id,
    )

    return db.scalar(stmt)

# ============================================================
# ACUMULADO DE UNA META
# ============================================================

def calcular_acumulado_meta(
    db: Session,
    id_meta: UUID,
) -> Decimal:

    aportes = func.coalesce(
        func.sum(AsignacionMeta.monto_asignacion).filter(
            AsignacionMeta.tipo_asignacion
            == TipoAsignacion.APORTE
        ),
        0,
    )

    retiros = func.coalesce(
        func.sum(AsignacionMeta.monto_asignacion).filter(
            AsignacionMeta.tipo_asignacion
            == TipoAsignacion.RETIRO
        ),
        0,
    )

    stmt = (
        select(aportes - retiros)
        .where(
            AsignacionMeta.meta_id == id_meta
        )
    )

    resultado = db.scalar(stmt)

    return Decimal(resultado or 0)


# ============================================================
# RESERVA TOTAL DE UNA CUENTA
# ============================================================

def calcular_reserva_total_cuenta(
    db: Session,
    usuario_id: UUID,
    cuenta_id: UUID,
) -> Decimal:

    stmt = (
        select(
            func.coalesce(
                func.sum(
                    AsignacionMeta.monto_asignacion
                ).filter(
                    AsignacionMeta.tipo_asignacion
                    == TipoAsignacion.APORTE
                ),
                0,
            )
            -
            func.coalesce(
                func.sum(
                    AsignacionMeta.monto_asignacion
                ).filter(
                    AsignacionMeta.tipo_asignacion
                    == TipoAsignacion.RETIRO
                ),
                0,
            )
        )
        .select_from(Meta)
        .outerjoin(
            AsignacionMeta,
            AsignacionMeta.meta_id == Meta.id_meta,
        )
        .where(
            Meta.usuario_id == usuario_id,
            Meta.cuenta_id == cuenta_id,
            Meta.estado_meta == EstadoMeta.ACTIVA,
        )
    )

    resultado = db.scalar(stmt)

    return Decimal(resultado or 0)


# ============================================================
# SALDO REAL DE CUENTA
# ============================================================

def calcular_saldo_real_cuenta(
    db: Session,
    cuenta: Cuenta,
) -> Decimal:
    """
    Las metas solo pueden pertenecer a cuentas no crediticias.

    Reutilizamos el cálculo del módulo Transacción para evitar
    implementar una segunda fórmula de saldo.
    """

    return calcular_saldo_actual(
        db,
        cuenta,
    )


# ============================================================
# LISTAR METAS
# ============================================================

def listar_metas(
    db: Session,
    usuario_id: UUID,
    estado: EstadoMeta | None,
    cuenta_id: UUID | None,
    limite: int,
    offset: int,
):
    filtros = [
        Meta.usuario_id == usuario_id,
    ]

    if estado is not None:
        filtros.append(
            Meta.estado_meta == estado
        )

    if cuenta_id is not None:
        filtros.append(
            Meta.cuenta_id == cuenta_id
        )

    total = (
        db.scalar(
            select(func.count())
            .select_from(Meta)
            .where(*filtros)
        )
        or 0
    )

    stmt = (
        select(Meta)
        .where(*filtros)
        .order_by(
            Meta.fecha_creacion_meta.desc(),
            Meta.id_meta.desc(),
        )
        .limit(limite)
        .offset(offset)
    )

    metas = list(
        db.scalars(stmt).all()
    )

    return metas, total


# ============================================================
# ACTUALIZAR META
# ============================================================

def actualizar_meta(
    db: Session,
    meta: Meta,
):
    db.add(meta)
    db.flush()


# ============================================================
# ASIGNACIONES
# ============================================================

def agregar_asignacion(
    db: Session,
    asignacion: AsignacionMeta,
):
    db.add(asignacion)
    db.flush()


def listar_asignaciones(
    db: Session,
    id_meta: UUID,
    tipo_asignacion: TipoAsignacion | None,
    limite: int,
    offset: int,
):
    filtros = [
        AsignacionMeta.meta_id == id_meta,
    ]

    if tipo_asignacion is not None:
        filtros.append(
            AsignacionMeta.tipo_asignacion
            == tipo_asignacion
        )

    total = (
        db.scalar(
            select(func.count())
            .select_from(AsignacionMeta)
            .where(*filtros)
        )
        or 0
    )

    stmt = (
        select(AsignacionMeta)
        .where(*filtros)
        .order_by(
            AsignacionMeta
            .fecha_registro_asignacion
            .desc(),
            AsignacionMeta
            .id_asignacion
            .desc(),
        )
        .limit(limite)
        .offset(offset)
    )

    asignaciones = list(
        db.scalars(stmt).all()
    )

    return asignaciones, total