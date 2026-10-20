from uuid import UUID

from sqlalchemy import func, select, text
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
    db.flush()
    db.refresh(cuenta)

    return cuenta


def actualizar(
    db: Session,
    cuenta: Cuenta,
    cambios: dict,
) -> Cuenta:

    for campo, valor in cambios.items():
        setattr(cuenta, campo, valor)

    db.flush()
    db.refresh(cuenta)

    return cuenta


def cambiar_estado(
    db: Session,
    cuenta: Cuenta,
    es_activa: bool,
) -> Cuenta:

    cuenta.es_activa_cuenta = es_activa

    db.flush()
    db.refresh(cuenta)

    return cuenta

def obtener_estado_financiero_cuenta(
    db: Session,
    id_cuenta: UUID,
    usuario_id: UUID,
) -> dict | None:

    consulta = text("""
        SELECT *
        FROM public.vw_estado_financiero_cuenta
        WHERE id_cuenta = :id_cuenta
          AND usuario_id = :usuario_id
    """)

    resultado = db.execute(
        consulta,
        {
            "id_cuenta": id_cuenta,
            "usuario_id": usuario_id,
        },
    ).mappings().one_or_none()

    return (
        dict(resultado)
        if resultado is not None
        else None
    )


def listar_estados_financieros_cuentas(
    db: Session,
    usuario_id: UUID,
) -> dict[UUID, dict]:

    consulta = text("""
        SELECT *
        FROM public.vw_estado_financiero_cuenta
        WHERE usuario_id = :usuario_id
    """)

    resultados = db.execute(
        consulta,
        {"usuario_id": usuario_id},
    ).mappings().all()

    return {
        fila["id_cuenta"]: dict(fila)
        for fila in resultados
    }


def bloquear_usuario_v11(
    db: Session,
    usuario_id: UUID,
) -> None:
    db.execute(
        text("""
            SELECT public.fn_usuario_lock_v11(
                :usuario_id,
                true
            )
        """),
        {"usuario_id": usuario_id},
    )


def cuenta_tiene_transacciones(
    db: Session,
    id_cuenta: UUID,
    usuario_id: UUID,
) -> bool:

    resultado = db.scalar(
        text("""
            SELECT EXISTS (
                SELECT 1
                FROM public.transaccion
                WHERE usuario_id = :usuario_id
                  AND (
                      cuenta_id = :id_cuenta
                      OR cuenta_destino_id = :id_cuenta
                  )
            )
        """),
        {
            "usuario_id": usuario_id,
            "id_cuenta": id_cuenta,
        },
    )

    return bool(resultado)
