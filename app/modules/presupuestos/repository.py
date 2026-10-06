from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.categorias.model import Categoria
from app.modules.presupuestos.model import (
    DetallePresupuesto,
    EstadoPresupuesto,
    Presupuesto,
)
from app.modules.transacciones.model import (
    TipoTransaccion,
    Transaccion,
)
from app.modules.usuarios.model import Usuario


# =========================================================
# BLOQUEOS
# =========================================================

def bloquear_usuario(
    db: Session,
    usuario_id: UUID,
):
    stmt = (
        select(Usuario)
        .where(
            Usuario.id_usuario == usuario_id,
        )
        .with_for_update()
    )

    return db.scalar(stmt)


def bloquear_categorias(
    db: Session,
    usuario_id: UUID,
    categorias_ids: list[UUID],
):
    """
    Bloquea las categorías en un orden determinista para reducir
    el riesgo de deadlocks.
    """

    if not categorias_ids:
        return []

    ids_ordenados = sorted(
        set(categorias_ids),
        key=str,
    )

    stmt = (
        select(Categoria)
        .where(
            Categoria.usuario_id == usuario_id,
            Categoria.id_categoria.in_(ids_ordenados),
        )
        .order_by(Categoria.id_categoria.asc())
        .with_for_update()
    )

    return list(db.scalars(stmt).all())


def bloquear_presupuesto(
    db: Session,
    usuario_id: UUID,
    id_presupuesto: UUID,
):
    stmt = (
        select(Presupuesto)
        .where(
            Presupuesto.id_presupuesto == id_presupuesto,
            Presupuesto.usuario_id == usuario_id,
        )
        .with_for_update()
    )

    return db.scalar(stmt)


# =========================================================
# PRESUPUESTOS
# =========================================================

def obtener_presupuesto_por_id(
    db: Session,
    usuario_id: UUID,
    id_presupuesto: UUID,
):
    stmt = select(Presupuesto).where(
        Presupuesto.id_presupuesto == id_presupuesto,
        Presupuesto.usuario_id == usuario_id,
    )

    return db.scalar(stmt)


def obtener_presupuesto_activo(
    db: Session,
    usuario_id: UUID,
):
    stmt = select(Presupuesto).where(
        Presupuesto.usuario_id == usuario_id,
        Presupuesto.estado_presupuesto == EstadoPresupuesto.ACTIVO,
    )

    return db.scalar(stmt)


def agregar_presupuesto(
    db: Session,
    presupuesto: Presupuesto,
):
    db.add(presupuesto)
    db.flush()


def agregar_detalles(
    db: Session,
    detalles: list[DetallePresupuesto],
):
    db.add_all(detalles)
    db.flush()


def actualizar_presupuesto(
    db: Session,
    presupuesto: Presupuesto,
):
    db.add(presupuesto)
    db.flush()


# =========================================================
# DETALLES
# =========================================================

def obtener_detalles_presupuesto(
    db: Session,
    id_presupuesto: UUID,
):
    stmt = (
        select(
            DetallePresupuesto,
            Categoria.nombre_categoria,
        )
        .join(
            Categoria,
            Categoria.id_categoria
            == DetallePresupuesto.categoria_id,
        )
        .where(
            DetallePresupuesto.presupuesto_id
            == id_presupuesto,
        )
        .order_by(
            DetallePresupuesto.categoria_id.asc(),
        )
    )

    return db.execute(stmt).all()


def obtener_categorias_presupuesto(
    db: Session,
    id_presupuesto: UUID,
) -> set[UUID]:
    stmt = select(
        DetallePresupuesto.categoria_id
    ).where(
        DetallePresupuesto.presupuesto_id
        == id_presupuesto,
    )

    return set(db.scalars(stmt).all())


# =========================================================
# LISTADO DE PRESUPUESTOS
# =========================================================

def listar_presupuestos(
    db: Session,
    usuario_id: UUID,
    estado: EstadoPresupuesto | None,
    limite: int,
    offset: int,
):
    filtros = [
        Presupuesto.usuario_id == usuario_id,
    ]

    if estado is not None:
        filtros.append(
            Presupuesto.estado_presupuesto == estado
        )

    stmt_total = (
        select(func.count())
        .select_from(Presupuesto)
        .where(*filtros)
    )

    total = db.scalar(stmt_total) or 0

    stmt = (
        select(Presupuesto)
        .where(*filtros)
        .order_by(
            Presupuesto.fecha_inicio_presupuesto.desc(),
            Presupuesto.id_presupuesto.desc(),
        )
        .limit(limite)
        .offset(offset)
    )

    presupuestos = list(
        db.scalars(stmt).all()
    )

    return presupuestos, total


# =========================================================
# CONSUMO
# =========================================================

def calcular_consumo_total(
    db: Session,
    usuario_id: UUID,
    inicio: datetime,
    fin_exclusivo: datetime,
) -> Decimal:
    """
    Suma todos los GASTOS del usuario dentro de la ventana.
    Incluye categorías presupuestadas y no presupuestadas.
    """

    stmt = select(
        func.coalesce(
            func.sum(Transaccion.monto_transaccion),
            0,
        )
    ).where(
        Transaccion.usuario_id == usuario_id,
        Transaccion.tipo_transaccion == TipoTransaccion.GASTO,
        Transaccion.fecha_registro_transaccion >= inicio,
        Transaccion.fecha_registro_transaccion < fin_exclusivo,
    )

    return Decimal(db.scalar(stmt) or 0)


def calcular_consumos_por_categoria(
    db: Session,
    usuario_id: UUID,
    inicio: datetime,
    fin_exclusivo: datetime,
) -> dict[UUID, Decimal]:
    """
    Devuelve:
        {
            categoria_id: consumo,
            ...
        }

    Solo considera GASTOS.
    """

    stmt = (
        select(
            Transaccion.categoria_id,
            func.sum(
                Transaccion.monto_transaccion
            ).label("consumo"),
        )
        .where(
            Transaccion.usuario_id == usuario_id,
            Transaccion.tipo_transaccion == TipoTransaccion.GASTO,
            Transaccion.fecha_registro_transaccion >= inicio,
            Transaccion.fecha_registro_transaccion < fin_exclusivo,
            Transaccion.categoria_id.is_not(None),
        )
        .group_by(
            Transaccion.categoria_id,
        )
    )

    resultado = db.execute(stmt).all()

    return {
        categoria_id: Decimal(consumo)
        for categoria_id, consumo in resultado
    }


def calcular_consumo_presupuestado(
    db: Session,
    usuario_id: UUID,
    id_presupuesto: UUID,
    inicio: datetime,
    fin_exclusivo: datetime,
) -> Decimal:
    """
    Suma los gastos cuyas categorías forman parte
    de la distribución del presupuesto.
    """

    categorias_presupuestadas = (
        select(
            DetallePresupuesto.categoria_id
        )
        .where(
            DetallePresupuesto.presupuesto_id
            == id_presupuesto,
        )
    )

    stmt = select(
        func.coalesce(
            func.sum(Transaccion.monto_transaccion),
            0,
        )
    ).where(
        Transaccion.usuario_id == usuario_id,
        Transaccion.tipo_transaccion == TipoTransaccion.GASTO,
        Transaccion.fecha_registro_transaccion >= inicio,
        Transaccion.fecha_registro_transaccion < fin_exclusivo,
        Transaccion.categoria_id.in_(
            categorias_presupuestadas
        ),
    )

    return Decimal(db.scalar(stmt) or 0)


# =========================================================
# GASTOS DEL PRESUPUESTO
# =========================================================

def listar_gastos_presupuesto(
    db: Session,
    usuario_id: UUID,
    id_presupuesto: UUID,
    inicio: datetime,
    fin_exclusivo: datetime,
    alcance: str,
    categoria_id: UUID | None,
    limite: int,
    offset: int,
):
    categorias_presupuestadas = (
        select(
            DetallePresupuesto.categoria_id
        )
        .where(
            DetallePresupuesto.presupuesto_id
            == id_presupuesto,
        )
    )

    filtros = [
        Transaccion.usuario_id == usuario_id,
        Transaccion.tipo_transaccion == TipoTransaccion.GASTO,
        Transaccion.fecha_registro_transaccion >= inicio,
        Transaccion.fecha_registro_transaccion < fin_exclusivo,
    ]

    if alcance == "PRESUPUESTADOS":
        filtros.append(
            Transaccion.categoria_id.in_(
                categorias_presupuestadas
            )
        )

    elif alcance == "NO_PRESUPUESTADOS":
        filtros.append(
            or_(
                Transaccion.categoria_id.is_(None),
                ~Transaccion.categoria_id.in_(
                    categorias_presupuestadas
                ),
            )
        )

    if categoria_id is not None:
        filtros.append(
            Transaccion.categoria_id == categoria_id
        )

    stmt_total = (
        select(func.count())
        .select_from(Transaccion)
        .where(*filtros)
    )

    total = db.scalar(stmt_total) or 0

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

    gastos = list(
        db.scalars(stmt).all()
    )

    return gastos, total