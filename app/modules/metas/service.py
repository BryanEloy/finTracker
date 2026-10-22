from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.modules.metas import repository
from app.modules.metas.model import Meta, AsignacionMeta, EstadoMeta, TipoAsignacion
from app.modules.metas.schemas import AccionCierre

ZONA_NEGOCIO = ZoneInfo("America/Mexico_City")
CERO = Decimal("0.00")

class MetaNoEncontradaError(Exception): pass
class CuentaNoEncontradaError(Exception): pass
class CuentaInactivaError(Exception): pass
class NombreMetaDuplicadoError(Exception): pass
class MetaCerradaError(Exception): pass
class MetaVencidaError(Exception): pass
class MetaNoFinalizableError(Exception): pass
class FondosLibresInsuficientesError(Exception): pass
class AporteSuperaObjetivoError(Exception): pass
class RetiroSuperaAcumuladoError(Exception): pass
class DatosInvalidosError(Exception): pass
class UsuarioDesactivadoError(Exception): pass


def hoy_negocio():
    return datetime.now(ZONA_NEGOCIO).date()


def valor_enum(valor):
    return getattr(valor, "value", valor)


def activa(meta):
    return valor_enum(meta.estado_meta) == "ACTIVA"


def centavos(valor):
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def salida_meta(db, meta):
    resumen = repository.obtener_resumen_meta(db, meta.usuario_id, meta.id_meta)
    if resumen is None: raise RuntimeError("Resumen de meta V1.1 no disponible")
    return dict(resumen)


def validar_cuenta(cuenta, exigir_activa=True):
    if cuenta is None: raise CuentaNoEncontradaError()
    if valor_enum(cuenta.tipo_cuenta) == "CREDITO": raise DatosInvalidosError()
    if exigir_activa and not cuenta.es_activa_cuenta: raise CuentaInactivaError()


def manejar_integridad(error):
    nombre = getattr(getattr(error.orig, "diag", None), "constraint_name", "")
    if nombre == "uq_meta_usuario_nombre_ci": raise NombreMetaDuplicadoError() from error
    raise DatosInvalidosError() from error


def crear_meta(db: Session, usuario_id: UUID, cuenta_id: UUID | None, nombre_meta: str, monto_objetivo_meta: Decimal, fecha_limite_meta, descripcion_meta: str | None):
    try:
        usuario = repository.bloquear_usuario(db, usuario_id)
        if usuario is None or not usuario.es_activo_usuario: raise UsuarioDesactivadoError()
        if fecha_limite_meta < hoy_negocio(): raise DatosInvalidosError()
        if cuenta_id is not None:
            cuenta = repository.obtener_cuenta_propia(db, usuario_id, cuenta_id)
            validar_cuenta(cuenta)
        if repository.existe_nombre_meta(db, usuario_id, nombre_meta): raise NombreMetaDuplicadoError()
        meta = Meta(usuario_id=usuario_id, cuenta_id=cuenta_id, nombre_meta=nombre_meta, monto_objetivo_meta=monto_objetivo_meta, fecha_limite_meta=fecha_limite_meta, descripcion_meta=descripcion_meta)
        repository.agregar_meta(db, meta)
        db.commit()
        return salida_meta(db, meta)
    except IntegrityError as exc:
        db.rollback(); manejar_integridad(exc)
    except Exception:
        db.rollback(); raise


def listar_metas(db, usuario_id, estado, cuenta_id, limite, offset):
    if cuenta_id is not None and repository.obtener_cuenta_propia(db, usuario_id, cuenta_id) is None: raise CuentaNoEncontradaError()
    metas, total = repository.listar_metas(db, usuario_id, estado, cuenta_id, limite, offset)
    return [salida_meta(db, m) for m in metas], total


def obtener_detalle_meta(db, usuario_id, id_meta):
    meta = repository.obtener_meta_por_id(db, usuario_id, id_meta)
    if meta is None: raise MetaNoEncontradaError()
    cuenta = repository.obtener_cuenta_propia(db, usuario_id, meta.cuenta_id) if meta.cuenta_id else None
    estado = repository.obtener_estado_financiero_cuenta(db, usuario_id, cuenta.id_cuenta) if cuenta else None
    resumen_cuenta = None
    if estado is not None:
        saldo = Decimal(estado["saldo_actual_cuenta"] or 0)
        reserva = Decimal(estado["reserva_total_cuenta"] or 0)
        libre = Decimal(estado["dinero_libre_cuenta"] or 0)
        resumen_cuenta = {"saldo_actual_cuenta":saldo,"reserva_total_cuenta":reserva,"dinero_libre_cuenta":libre,"disponible_para_aportar":max(libre,CERO),"deficit_reservas_cuenta":max(-libre,CERO)}
    return {"meta":salida_meta(db,meta), "resumen_cuenta":resumen_cuenta, "reservas_por_cuenta":repository.reservas_por_meta(db,usuario_id,id_meta)}


def actualizar_meta(db, usuario_id, id_meta, datos):
    try:
        usuario = repository.bloquear_usuario(db, usuario_id)
        if usuario is None or not usuario.es_activo_usuario: raise UsuarioDesactivadoError()
        meta = repository.bloquear_meta(db, usuario_id, id_meta)
        if meta is None: raise MetaNoEncontradaError()
        if not activa(meta): raise MetaCerradaError()
        if "nombre_meta" in datos.model_fields_set:
            if repository.existe_nombre_meta(db,usuario_id,datos.nombre_meta,meta.id_meta): raise NombreMetaDuplicadoError()
            meta.nombre_meta = datos.nombre_meta
        if "descripcion_meta" in datos.model_fields_set: meta.descripcion_meta = datos.descripcion_meta
        repository.actualizar_meta(db,meta)
        db.commit()
        return salida_meta(db,meta)
    except IntegrityError as exc:
        db.rollback(); manejar_integridad(exc)
    except Exception:
        db.rollback(); raise


def cerrar_meta(db, usuario_id, id_meta, accion):
    try:
        usuario = repository.bloquear_usuario(db, usuario_id)
        if usuario is None or not usuario.es_activo_usuario: raise UsuarioDesactivadoError()
        meta = repository.bloquear_meta(db, usuario_id, id_meta)
        if meta is None: raise MetaNoEncontradaError()
        estado = valor_enum(meta.estado_meta)
        if accion == AccionCierre.CANCELAR and estado == "CANCELADA":
            db.commit(); return salida_meta(db,meta)
        if accion == AccionCierre.FINALIZAR and estado in ("ALCANZADA","NO_ALCANZADA"):
            db.commit(); return salida_meta(db,meta)
        if estado != "ACTIVA": raise MetaCerradaError()
        acumulado = repository.calcular_acumulado_meta(db,id_meta)
        if accion == AccionCierre.CANCELAR:
            meta.estado_meta = EstadoMeta.CANCELADA
        elif accion == AccionCierre.FINALIZAR:
            if acumulado == Decimal(meta.monto_objetivo_meta): meta.estado_meta = EstadoMeta.ALCANZADA
            elif acumulado < Decimal(meta.monto_objetivo_meta) and hoy_negocio() > meta.fecha_limite_meta: meta.estado_meta = EstadoMeta.NO_ALCANZADA
            else: raise MetaNoFinalizableError()
        else: raise DatosInvalidosError()
        meta.fecha_cierre_meta = datetime.now(ZONA_NEGOCIO)
        repository.actualizar_meta(db,meta)
        db.commit()
        return salida_meta(db,meta)
    except Exception:
        db.rollback(); raise


def crear_asignacion(db, usuario_id, id_meta, cuenta_id, tipo_asignacion, monto_asignacion, comentario_asignacion):
    try:
        usuario = repository.bloquear_usuario(db, usuario_id)
        if usuario is None or not usuario.es_activo_usuario: raise UsuarioDesactivadoError()
        # Bloqueo de cuenta antes de meta, compatible con el orden de operaciones V1.1.
        cuenta = repository.bloquear_cuenta(db, usuario_id, cuenta_id)
        if cuenta is None: raise CuentaNoEncontradaError()
        meta = repository.bloquear_meta(db, usuario_id, id_meta)
        if meta is None: raise MetaNoEncontradaError()
        if not activa(meta): raise MetaCerradaError()
        if hoy_negocio() > meta.fecha_limite_meta: raise MetaVencidaError()
        if valor_enum(cuenta.tipo_cuenta) == "CREDITO": raise DatosInvalidosError()
        acumulado = repository.calcular_acumulado_meta(db,id_meta)
        if tipo_asignacion == TipoAsignacion.APORTE:
            if not cuenta.es_activa_cuenta: raise CuentaInactivaError()
            if monto_asignacion > Decimal(meta.monto_objetivo_meta) - acumulado: raise AporteSuperaObjetivoError()
            estado = repository.obtener_estado_financiero_cuenta(db,usuario_id,cuenta_id)
            if estado is None or estado["dinero_libre_cuenta"] is None: raise RuntimeError("Estado financiero no disponible")
            if monto_asignacion > max(Decimal(estado["dinero_libre_cuenta"]), CERO): raise FondosLibresInsuficientesError()
        elif tipo_asignacion == TipoAsignacion.RETIRO:
            reserva = repository.reserva_cuenta_en_meta(db,usuario_id,id_meta,cuenta_id)
            if monto_asignacion > reserva: raise RetiroSuperaAcumuladoError()
        else: raise DatosInvalidosError()
        asignacion = AsignacionMeta(meta_id=id_meta,usuario_id=usuario_id,cuenta_id=cuenta_id,tipo_asignacion=tipo_asignacion,monto_asignacion=monto_asignacion,comentario_asignacion=comentario_asignacion)
        repository.agregar_asignacion(db,asignacion)
        db.commit()
        db.refresh(asignacion)
        return asignacion
    except IntegrityError as exc:
        db.rollback(); raise DatosInvalidosError() from exc
    except Exception:
        db.rollback(); raise


def listar_asignaciones(db, usuario_id, id_meta, tipo_asignacion, limite, offset):
    if repository.obtener_meta_por_id(db,usuario_id,id_meta) is None: raise MetaNoEncontradaError()
    return repository.listar_asignaciones(db,id_meta,tipo_asignacion,limite,offset)
