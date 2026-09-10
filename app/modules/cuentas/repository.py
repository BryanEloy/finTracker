from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.cuentas.model import Cuenta


def obtener_por_id(
    db: Session,
    id_cuenta: UUID,
    usuario_id: UUID,
) -> Cuenta | None:

    return db.scalar(
        select(Cuenta).where(
            Cuenta.id_cuenta == id_cuenta,
            Cuenta.usuario_id == usuario_id,
        )
    )


def obtener_por_nombre(
    db: Session,
    usuario_id: UUID,
    nombre_cuenta: str,
) -> Cuenta | None:

    return db.scalar(
        select(Cuenta).where(
            Cuenta.usuario_id == usuario_id,
            func.lower(Cuenta.nombre_cuenta)
            == nombre_cuenta.lower(),
        )
    )


def listar(
    db: Session,
    usuario_id: UUID,
) -> list[Cuenta]:

    return list(
        db.scalars(
            select(Cuenta)
            .where(
                Cuenta.usuario_id == usuario_id
            )
            .order_by(
                Cuenta.fecha_creacion_cuenta.asc()
            )
        ).all()
    )


def crear(
    db: Session,
    cuenta: Cuenta,
) -> Cuenta:

    db.add(cuenta)

    try:
        db.commit()
        db.refresh(cuenta)

        return cuenta

    except IntegrityError:
        db.rollback()
        raise


def actualizar(
    db: Session,
    cuenta: Cuenta,
    cambios: dict,
) -> Cuenta:

    for campo, valor in cambios.items():
        setattr(
            cuenta,
            campo,
            valor,
        )

    try:
        db.commit()
        db.refresh(cuenta)

        return cuenta

    except IntegrityError:
        db.rollback()
        raise


def cambiar_estado(
    db: Session,
    cuenta: Cuenta,
    es_activa: bool,
) -> Cuenta:

    cuenta.es_activa_cuenta = es_activa

    db.commit()
    db.refresh(cuenta)

    return cuenta