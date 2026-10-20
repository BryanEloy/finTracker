from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.modules.cuentas.model import Cuenta
from app.modules.transacciones.model import TipoTransaccion, Transaccion


def bloquear_usuario(db: Session, usuario_id: UUID) -> None:
    # Requiere transacciones READ COMMITTED; no confirmar aquí.
    db.execute(text("SELECT public.fn_usuario_lock_v11(:usuario_id, true)"), {"usuario_id": usuario_id})


def bloquear_cuentas(db: Session, usuario_id: UUID, ids_cuentas: list[UUID]) -> dict[UUID, Cuenta]:
    ids = sorted(set(ids_cuentas))
    stmt = (
        select(Cuenta)
        .where(Cuenta.usuario_id == usuario_id, Cuenta.id_cuenta.in_(ids))
        .order_by(Cuenta.id_cuenta)
        .with_for_update()
    )
    return {cuenta.id_cuenta: cuenta for cuenta in db.scalars(stmt).all()}


def obtener_cuenta_propia(db: Session, usuario_id: UUID, id_cuenta: UUID) -> Cuenta | None:
    return db.scalar(select(Cuenta).where(Cuenta.usuario_id == usuario_id, Cuenta.id_cuenta == id_cuenta))


def obtener_estado_financiero_cuenta(db: Session, usuario_id: UUID, id_cuenta: UUID) -> dict | None:
    fila = db.execute(
        text("""SELECT * FROM public.vw_estado_financiero_cuenta
                WHERE usuario_id = :usuario_id AND id_cuenta = :id_cuenta"""),
        {"usuario_id": usuario_id, "id_cuenta": id_cuenta},
    ).mappings().one_or_none()
    return dict(fila) if fila is not None else None


def agregar_transaccion(db: Session, transaccion: Transaccion) -> None:
    db.add(transaccion)
    db.flush()  # Ejecuta trigger y restricciones; commit corresponde al servicio.


def obtener_transaccion_por_id(db: Session, usuario_id: UUID, id_transaccion: UUID) -> Transaccion | None:
    return db.scalar(select(Transaccion).where(
        Transaccion.usuario_id == usuario_id,
        Transaccion.id_transaccion == id_transaccion,
    ))


def listar_transacciones(
    db: Session,
    usuario_id: UUID,
    tipo_transaccion: TipoTransaccion | None,
    cuenta_id: UUID | None,
    limite: int,
    offset: int,
) -> tuple[list[Transaccion], int]:
    filtros = [Transaccion.usuario_id == usuario_id]
    if tipo_transaccion is not None:
        filtros.append(Transaccion.tipo_transaccion == tipo_transaccion)
    if cuenta_id is not None:
        filtros.append(or_(Transaccion.cuenta_id == cuenta_id, Transaccion.cuenta_destino_id == cuenta_id))
    total = db.scalar(select(func.count()).select_from(Transaccion).where(*filtros)) or 0
    registros = list(db.scalars(
        select(Transaccion).where(*filtros)
        .order_by(Transaccion.fecha_registro_transaccion.desc(), Transaccion.id_transaccion.desc())
        .limit(limite).offset(offset)
    ).all())
    return registros, total
