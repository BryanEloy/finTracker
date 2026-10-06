from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.metas import repository
from app.modules.metas.model import (
    AsignacionMeta,
    EstadoMeta,
    Meta,
    TipoAsignacion,
)
from app.modules.metas.schemas import AccionCierre


ZONA_NEGOCIO = ZoneInfo("America/Mexico_City")

CERO = Decimal("0.00")
CIEN = Decimal("100.00")


# ============================================================
# EXCEPCIONES
# ============================================================

class MetaNoEncontradaError(Exception):
    pass


class CuentaNoEncontradaError(Exception):
    pass


class CuentaInactivaError(Exception):
    pass


class NombreMetaDuplicadoError(Exception):
    pass


class MetaCerradaError(Exception):
    pass


class MetaVencidaError(Exception):
    pass


class MetaNoFinalizableError(Exception):
    pass


class FondosLibresInsuficientesError(Exception):
    pass


class AporteSuperaObjetivoError(Exception):
    pass


class RetiroSuperaAcumuladoError(Exception):
    pass


class DatosInvalidosError(Exception):
    pass

class UsuarioDesactivadoError(Exception):
    pass


# ============================================================
# FECHA DE NEGOCIO
# ============================================================

def hoy_negocio():
    return datetime.now(ZONA_NEGOCIO).date()


# ============================================================
# AUXILIARES
# ============================================================

def obtener_valor_enum(valor):
    return getattr(valor, "value", valor)


def es_cuenta_crediticia(cuenta) -> bool:
    return obtener_valor_enum(
        cuenta.tipo_cuenta
    ) == "CREDITO"


def esta_activa_cuenta(cuenta) -> bool:
    return bool(cuenta.es_activa_cuenta)


def esta_activa_meta(meta: Meta) -> bool:
    return (
        obtener_valor_enum(meta.estado_meta)
        == EstadoMeta.ACTIVA.value
    )


def meta_esta_vencida(meta: Meta) -> bool:
    return (
        esta_activa_meta(meta)
        and hoy_negocio() > meta.fecha_limite_meta
    )


def decimal_dos(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


# ============================================================
# CÁLCULOS DE META
# ============================================================

def construir_meta_salida(
    db: Session,
    meta: Meta,
):
    acumulado = repository.calcular_acumulado_meta(
        db,
        meta.id_meta,
    )

    objetivo = Decimal(
        meta.monto_objetivo_meta
    )

    faltante = max(
        objetivo - acumulado,
        CERO,
    )

    porcentaje = (
        acumulado / objetivo
    ) * Decimal("100")

    porcentaje = decimal_dos(porcentaje)

    reserva_vigente = (
        acumulado
        if esta_activa_meta(meta)
        else CERO
    )

    return {
        "id_meta": meta.id_meta,
        "cuenta_id": meta.cuenta_id,
        "nombre_meta": meta.nombre_meta,
        "descripcion_meta": meta.descripcion_meta,

        "monto_objetivo_meta":
            decimal_dos(objetivo),

        "fecha_limite_meta":
            meta.fecha_limite_meta,

        "fecha_creacion_meta":
            meta.fecha_creacion_meta,

        "fecha_cierre_meta":
            meta.fecha_cierre_meta,

        "estado_meta":
            meta.estado_meta,

        "monto_actual_meta":
            decimal_dos(acumulado),

        "monto_faltante_meta":
            decimal_dos(faltante),

        "porcentaje_avance_meta":
            porcentaje,

        "reserva_vigente_meta":
            decimal_dos(reserva_vigente),

        "plazo_vencido":
            meta_esta_vencida(meta),
    }


# ============================================================
# RESUMEN DE CUENTA
# ============================================================

def construir_resumen_cuenta(
    db: Session,
    cuenta,
):
    saldo_actual = (
        repository.calcular_saldo_real_cuenta(
            db,
            cuenta,
        )
    )

    reserva_total = (
        repository.calcular_reserva_total_cuenta(
            db,
            cuenta.usuario_id,
            cuenta.id_cuenta,
        )
    )

    dinero_libre = (
        saldo_actual - reserva_total
    )

    disponible = max(
        dinero_libre,
        CERO,
    )

    deficit = max(
        -dinero_libre,
        CERO,
    )

    return {
        "saldo_actual_cuenta":
            decimal_dos(saldo_actual),

        "reserva_total_cuenta":
            decimal_dos(reserva_total),

        "dinero_libre_cuenta":
            decimal_dos(dinero_libre),

        "disponible_para_aportar":
            decimal_dos(disponible),

        "deficit_reservas_cuenta":
            decimal_dos(deficit),
    }


# ============================================================
# CREAR META
# ============================================================

def crear_meta(
    db: Session,
    usuario_id: UUID,
    cuenta_id: UUID,
    nombre_meta: str,
    monto_objetivo_meta: Decimal,
    fecha_limite_meta,
    descripcion_meta: str | None,
):
    try:
        cuenta = repository.obtener_cuenta_propia(
            db,
            usuario_id,
            cuenta_id,
        )

        if cuenta is None:
            raise CuentaNoEncontradaError()

        if not esta_activa_cuenta(cuenta):
            raise CuentaInactivaError()

        if es_cuenta_crediticia(cuenta):
            raise DatosInvalidosError()

        if fecha_limite_meta < hoy_negocio():
            raise DatosInvalidosError()

        if repository.existe_nombre_meta(
            db,
            usuario_id,
            cuenta_id,
            nombre_meta,
        ):
            raise NombreMetaDuplicadoError()

        meta = Meta(
            usuario_id=usuario_id,
            cuenta_id=cuenta_id,
            nombre_meta=nombre_meta,
            monto_objetivo_meta=monto_objetivo_meta,
            fecha_limite_meta=fecha_limite_meta,
            descripcion_meta=descripcion_meta,
        )

        repository.agregar_meta(
            db,
            meta,
        )

        db.commit()
        db.refresh(meta)

        return construir_meta_salida(
            db,
            meta,
        )

    except (
        CuentaNoEncontradaError,
        CuentaInactivaError,
        NombreMetaDuplicadoError,
        DatosInvalidosError,
    ):
        db.rollback()
        raise

    except IntegrityError as error:
        db.rollback()

        nombre_constraint = getattr(
            getattr(error.orig, "diag", None),
            "constraint_name",
            None,
        )

        if (
            nombre_constraint
            == "uq_meta_usuario_cuenta_nombre"
        ):
            raise NombreMetaDuplicadoError()

        raise DatosInvalidosError()
    
    except Exception:
            db.rollback()
            raise


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
    if cuenta_id is not None:
        cuenta = repository.obtener_cuenta_propia(
            db,
            usuario_id,
            cuenta_id,
        )

        if cuenta is None:
            raise CuentaNoEncontradaError()

    metas, total = repository.listar_metas(
        db,
        usuario_id,
        estado,
        cuenta_id,
        limite,
        offset,
    )

    resultados = [
        construir_meta_salida(db, meta)
        for meta in metas
    ]

    return resultados, total


# ============================================================
# DETALLE
# ============================================================

def obtener_detalle_meta(
    db: Session,
    usuario_id: UUID,
    id_meta: UUID,
):
    meta = repository.obtener_meta_por_id(
        db,
        usuario_id,
        id_meta,
    )

    if meta is None:
        raise MetaNoEncontradaError()

    cuenta = repository.obtener_cuenta_propia(
        db,
        usuario_id,
        meta.cuenta_id,
    )

    # La FK debería hacer imposible este caso.
    if cuenta is None:
        raise MetaNoEncontradaError()

    return {
        "meta": construir_meta_salida(
            db,
            meta,
        ),
        "resumen_cuenta":
            construir_resumen_cuenta(
                db,
                cuenta,
            ),
    }


# ============================================================
# EDITAR META
# ============================================================

def actualizar_meta(
    db: Session,
    usuario_id: UUID,
    id_meta: UUID,
    datos,
):
    try:
        meta = repository.bloquear_meta(
            db,
            usuario_id,
            id_meta,
        )

        if meta is None:
            raise MetaNoEncontradaError()

        if not esta_activa_meta(meta):
            raise MetaCerradaError()

        campos = datos.model_fields_set

        if "nombre_meta" in campos:
            if repository.existe_nombre_meta(
                db,
                usuario_id,
                meta.cuenta_id,
                datos.nombre_meta,
                excluir_id_meta=meta.id_meta,
            ):
                raise NombreMetaDuplicadoError()

            meta.nombre_meta = datos.nombre_meta

        if "descripcion_meta" in campos:
            meta.descripcion_meta = (
                datos.descripcion_meta
            )

        repository.actualizar_meta(
            db,
            meta,
        )

        db.commit()
        db.refresh(meta)

        return construir_meta_salida(
            db,
            meta,
        )

    except (
        MetaNoEncontradaError,
        MetaCerradaError,
        NombreMetaDuplicadoError,
    ):
        db.rollback()
        raise

    except IntegrityError as error:
        db.rollback()

        nombre_constraint = getattr(
            getattr(error.orig, "diag", None),
            "constraint_name",
            None,
        )

        if (
            nombre_constraint
            == "uq_meta_usuario_cuenta_nombre"
        ):
            raise NombreMetaDuplicadoError()

        raise DatosInvalidosError()

    except Exception:
        db.rollback()
        raise


# ============================================================
# CERRAR META
# ============================================================

def cerrar_meta(
    db: Session,
    usuario_id: UUID,
    id_meta: UUID,
    accion: AccionCierre,
):
    try:
        meta = repository.bloquear_meta(
            db,
            usuario_id,
            id_meta,
        )

        if meta is None:
            raise MetaNoEncontradaError()

        estado_actual = obtener_valor_enum(
            meta.estado_meta
        )

        # ----------------------------------------------------
        # IDEMPOTENCIA
        # ----------------------------------------------------

        if (
            accion == AccionCierre.CANCELAR
            and estado_actual
            == EstadoMeta.CANCELADA.value
        ):
            db.commit()

            return construir_meta_salida(
                db,
                meta,
            )

        if (
            accion == AccionCierre.FINALIZAR
            and estado_actual
            in (
                EstadoMeta.ALCANZADA.value,
                EstadoMeta.NO_ALCANZADA.value,
            )
        ):
            db.commit()

            return construir_meta_salida(
                db,
                meta,
            )

        if estado_actual != EstadoMeta.ACTIVA.value:
            raise MetaCerradaError()

        acumulado = (
            repository.calcular_acumulado_meta(
                db,
                meta.id_meta,
            )
        )

        objetivo = Decimal(
            meta.monto_objetivo_meta
        )

        # ----------------------------------------------------
        # CANCELAR
        # ----------------------------------------------------

        if accion == AccionCierre.CANCELAR:
            meta.estado_meta = (
                EstadoMeta.CANCELADA
            )

        # ----------------------------------------------------
        # FINALIZAR
        # ----------------------------------------------------

        elif accion == AccionCierre.FINALIZAR:

            if acumulado == objetivo:
                meta.estado_meta = (
                    EstadoMeta.ALCANZADA
                )

            elif (
                acumulado < objetivo
                and hoy_negocio()
                > meta.fecha_limite_meta
            ):
                meta.estado_meta = (
                    EstadoMeta.NO_ALCANZADA
                )

            else:
                raise MetaNoFinalizableError()

        else:
            raise DatosInvalidosError()

        meta.fecha_cierre_meta = datetime.now(
            ZONA_NEGOCIO
        )

        repository.actualizar_meta(
            db,
            meta,
        )

        db.commit()
        db.refresh(meta)

        return construir_meta_salida(
            db,
            meta,
        )

    except (
        MetaNoEncontradaError,
        MetaCerradaError,
        MetaNoFinalizableError,
        DatosInvalidosError,
    ):
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise


# ============================================================
# CREAR ASIGNACIÓN
# ============================================================

def crear_asignacion(
    db: Session,
    usuario_id: UUID,
    id_meta: UUID,
    tipo_asignacion: TipoAsignacion,
    monto_asignacion: Decimal,
    comentario_asignacion: str | None,
):
    try:
        # ----------------------------------------------------
        # 1. BLOQUEAR USUARIO
        # ----------------------------------------------------

        usuario = repository.bloquear_usuario(
            db,
            usuario_id,
        )

        if (
            usuario is None
            or not usuario.es_activo_usuario
        ):
            # Normalmente la dependencia JWT ya lo detectó.
            # Esta comprobación protege contra concurrencia.
            raise UsuarioDesactivadoError()

        # ----------------------------------------------------
        # 2. Localizar meta para conocer cuenta
        # ----------------------------------------------------

        meta_previa = repository.obtener_meta_por_id(
            db,
            usuario_id,
            id_meta,
        )

        if meta_previa is None:
            raise MetaNoEncontradaError()

        # ----------------------------------------------------
        # 3. BLOQUEAR CUENTA
        # ----------------------------------------------------

        cuenta = repository.bloquear_cuenta(
            db,
            usuario_id,
            meta_previa.cuenta_id,
        )

        if cuenta is None:
            raise MetaNoEncontradaError()

        # ----------------------------------------------------
        # 4. BLOQUEAR META
        # ----------------------------------------------------

        meta = repository.bloquear_meta(
            db,
            usuario_id,
            id_meta,
        )

        if meta is None:
            raise MetaNoEncontradaError()

        # ----------------------------------------------------
        # 5. ESTADO Y PLAZO
        # ----------------------------------------------------

        if not esta_activa_meta(meta):
            raise MetaCerradaError()

        if hoy_negocio() > meta.fecha_limite_meta:
            raise MetaVencidaError()

        # ----------------------------------------------------
        # 6. RECALCULAR ACUMULADO
        # ----------------------------------------------------

        acumulado = (
            repository.calcular_acumulado_meta(
                db,
                meta.id_meta,
            )
        )

        objetivo = Decimal(
            meta.monto_objetivo_meta
        )

        # ----------------------------------------------------
        # 7. APORTE
        # ----------------------------------------------------

        if tipo_asignacion == TipoAsignacion.APORTE:

            if not esta_activa_cuenta(cuenta):
                raise CuentaInactivaError()

            faltante = objetivo - acumulado

            if monto_asignacion > faltante:
                raise AporteSuperaObjetivoError()

            # IMPORTANTE:
            # Se calcula después de los bloqueos.
            saldo_real = (
                repository.calcular_saldo_real_cuenta(
                    db,
                    cuenta,
                )
            )

            reserva_total = (
                repository
                .calcular_reserva_total_cuenta(
                    db,
                    usuario_id,
                    cuenta.id_cuenta,
                )
            )

            disponible = max(
                saldo_real - reserva_total,
                CERO,
            )

            if monto_asignacion > disponible:
                raise FondosLibresInsuficientesError()

        # ----------------------------------------------------
        # 8. RETIRO
        # ----------------------------------------------------

        elif tipo_asignacion == TipoAsignacion.RETIRO:

            if monto_asignacion > acumulado:
                raise RetiroSuperaAcumuladoError()

            # Un retiro NO exige:
            # - cuenta activa
            # - saldo real suficiente

        else:
            raise DatosInvalidosError()

        # ----------------------------------------------------
        # 9. INSERT
        # ----------------------------------------------------

        asignacion = AsignacionMeta(
            meta_id=meta.id_meta,
            tipo_asignacion=tipo_asignacion,
            monto_asignacion=monto_asignacion,
            comentario_asignacion=
                comentario_asignacion,
        )

        repository.agregar_asignacion(
            db,
            asignacion,
        )

        # ----------------------------------------------------
        # 10. COMMIT
        # ----------------------------------------------------

        db.commit()
        db.refresh(asignacion)

        return asignacion

    except (
        UsuarioDesactivadoError,
        MetaNoEncontradaError,
        MetaCerradaError,
        MetaVencidaError,
        CuentaInactivaError,
        FondosLibresInsuficientesError,
        AporteSuperaObjetivoError,
        RetiroSuperaAcumuladoError,
        DatosInvalidosError,
    ):
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise DatosInvalidosError()

    except Exception:
        db.rollback()
        raise


# ============================================================
# LISTAR ASIGNACIONES
# ============================================================

def listar_asignaciones(
    db: Session,
    usuario_id: UUID,
    id_meta: UUID,
    tipo_asignacion: TipoAsignacion | None,
    limite: int,
    offset: int,
):
    meta = repository.obtener_meta_por_id(
        db,
        usuario_id,
        id_meta,
    )

    if meta is None:
        raise MetaNoEncontradaError()

    return repository.listar_asignaciones(
        db,
        id_meta,
        tipo_asignacion,
        limite,
        offset,
    )