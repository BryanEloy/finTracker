from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.usuarios.model import Usuario


def obtener_por_id(
    db: Session,
    id_usuario: UUID,
) -> Usuario | None:

    return db.scalar(
        select(Usuario).where(
            Usuario.id_usuario == id_usuario
        )
    )


def obtener_por_correo(
    db: Session,
    correo_usuario: str,
) -> Usuario | None:

    return db.scalar(
        select(Usuario).where(
            Usuario.correo_usuario == correo_usuario
        )
    )


def crear(
    db: Session,
    *,
    nombre_usuario: str,
    correo_usuario: str,
    password_hash_usuario: str,
) -> Usuario:

    usuario = Usuario(
        nombre_usuario=nombre_usuario,
        correo_usuario=correo_usuario,
        password_hash_usuario=password_hash_usuario,
    )

    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return usuario


def actualizar(
    db: Session,
    usuario: Usuario,
    cambios: dict,
) -> Usuario:

    for campo, valor in cambios.items():
        setattr(
            usuario,
            campo,
            valor,
        )

    db.commit()
    db.refresh(usuario)

    return usuario


def actualizar_password(
    db: Session,
    usuario: Usuario,
    password_hash_usuario: str,
) -> None:

    usuario.password_hash_usuario = (
        password_hash_usuario
    )

    db.commit()


def desactivar(
    db: Session,
    usuario: Usuario,
) -> None:

    usuario.es_activo_usuario = False

    usuario.fecha_desactivacion_usuario = (
        datetime.now(timezone.utc)
    )

    db.commit()


def reactivar(
    db: Session,
    usuario: Usuario,
) -> Usuario:
    """
    Reactiva exclusivamente al usuario autenticado.

    La función SQL recibe false para permitir
    el bloqueo de un usuario actualmente inactivo.
    """

    try:
        # La consulta inicial de autenticación puede haber
        # iniciado la transacción de SQLAlchemy.
        # El candado se adquiere antes de escribir.
        db.execute(
            text(
                "SELECT public.fn_usuario_lock_v11("
                ":id_usuario, false)"
            ),
            {"id_usuario": usuario.id_usuario},
        )

        # Releer el estado después de obtener el candado.
        db.refresh(usuario)

        if not usuario.es_activo_usuario:
            usuario.es_activo_usuario = True
            usuario.fecha_desactivacion_usuario = None

            db.commit()
            db.refresh(usuario)

        return usuario

    except Exception:
        db.rollback()
        raise


def obtener_resumen_dashboard(
    db: Session,
    id_usuario: UUID,
) -> dict | None:

    consulta = text("""
        SELECT
            id_usuario,
            saldo_total_usuario,
            reserva_total_usuario,
            dinero_libre_total_usuario,
            limite_credito_total_usuario,
            credito_utilizado_total_usuario,
            credito_disponible_total_usuario,
            porcentaje_utilizacion_credito_usuario
        FROM public.vw_estado_financiero_usuario
        WHERE id_usuario = :id_usuario
    """)

    resultado = db.execute(
        consulta,
        {"id_usuario": id_usuario},
    ).mappings().first()

    if resultado is None:
        return None

    return dict(resultado)


def obtener_periodo_activo_dashboard(
    db: Session,
    id_usuario: UUID,
) -> dict | None:

    consulta = text("""
        SELECT
            id_periodo,
            codigo_periodo,
            tipo_periodo,
            fecha_inicio_periodo,
            fecha_fin_periodo,
            estado_periodo,
            periodo_vencido,
            monto_total_presupuesto,
            ingresos_libres_periodo,
            ingresos_reservados_periodo,
            ingresos_reales_periodo,
            base_repartible_periodo,
            gasto_conocido_total_periodo,
            aplicado_total_periodo,
            ingresos_nueva_deuda_periodo,
            monto_presupuesto_periodo,
            monto_restante_periodo,
            monto_excedido_periodo,
            porcentaje_consumido_periodo,
            estado_consumo_periodo,
            pagos_deuda_periodo
        FROM public.vw_periodo_resumen_v11
        WHERE usuario_id = :id_usuario
          AND estado_periodo = 'ACTIVO'
    """)

    resultado = db.execute(
        consulta,
        {"id_usuario": id_usuario},
    ).mappings().one_or_none()

    if resultado is None:
        return None

    return dict(resultado)

