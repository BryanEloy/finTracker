from decimal import Decimal
from uuid import UUID
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.modules.cuentas.model import Cuenta
from app.modules.metas.model import Meta, AsignacionMeta, EstadoMeta, TipoAsignacion


def bloquear_usuario(db: Session, usuario_id: UUID):
    # Mismo bloqueo que los módulos de cuentas/transacciones V1.1.
    db.execute(text("SELECT public.fn_usuario_lock_v11(:uid, true)"), {"uid": usuario_id})
    from app.modules.usuarios.model import Usuario
    return db.scalar(select(Usuario).where(Usuario.id_usuario == usuario_id))


def bloquear_cuenta(db: Session, usuario_id: UUID, cuenta_id: UUID):
    return db.scalar(select(Cuenta).where(Cuenta.usuario_id == usuario_id, Cuenta.id_cuenta == cuenta_id).with_for_update())


def bloquear_meta(db: Session, usuario_id: UUID, id_meta: UUID):
    return db.scalar(select(Meta).where(Meta.usuario_id == usuario_id, Meta.id_meta == id_meta).with_for_update())


def obtener_meta_por_id(db, usuario_id, id_meta):
    return db.scalar(select(Meta).where(Meta.usuario_id == usuario_id, Meta.id_meta == id_meta))


def existe_nombre_meta(db, usuario_id, nombre_meta, excluir_id_meta=None):
    stmt = select(Meta.id_meta).where(Meta.usuario_id == usuario_id, func.lower(func.btrim(Meta.nombre_meta)) == nombre_meta.strip().lower())
    if excluir_id_meta is not None:
        stmt = stmt.where(Meta.id_meta != excluir_id_meta)
    return db.scalar(stmt) is not None


def agregar_meta(db, meta):
    db.add(meta)
    db.flush()


def obtener_cuenta_propia(db, usuario_id, cuenta_id):
    return db.scalar(select(Cuenta).where(Cuenta.usuario_id == usuario_id, Cuenta.id_cuenta == cuenta_id))


def obtener_resumen_meta(db, usuario_id, id_meta):
    return db.execute(text("SELECT * FROM public.vw_meta_resumen_v11 WHERE usuario_id=:uid AND id_meta=:mid"), {"uid":usuario_id,"mid":id_meta}).mappings().one_or_none()


def calcular_acumulado_meta(db, id_meta):
    return Decimal(db.scalar(text("SELECT monto_actual_meta FROM public.vw_meta_resumen_v11 WHERE id_meta=:mid"), {"mid":id_meta}) or 0)


def reservas_por_meta(db, usuario_id, id_meta):
    return [dict(x) for x in db.execute(text("SELECT cuenta_id, monto_actual_cuenta_meta, reserva_cuenta_en_meta FROM public.vw_reserva_meta_cuenta_v11 WHERE usuario_id=:uid AND meta_id=:mid ORDER BY cuenta_id"), {"uid":usuario_id,"mid":id_meta}).mappings()]


def reserva_cuenta_en_meta(db, usuario_id, id_meta, cuenta_id):
    return Decimal(db.scalar(text("SELECT reserva_cuenta_en_meta FROM public.vw_reserva_meta_cuenta_v11 WHERE usuario_id=:uid AND meta_id=:mid AND cuenta_id=:cid"), {"uid":usuario_id,"mid":id_meta,"cid":cuenta_id}) or 0)


def obtener_estado_financiero_cuenta(db, usuario_id, cuenta_id):
    row = db.execute(text("SELECT * FROM public.vw_estado_financiero_cuenta WHERE usuario_id=:uid AND id_cuenta=:cid"), {"uid":usuario_id,"cid":cuenta_id}).mappings().one_or_none()
    return dict(row) if row else None


def calcular_reserva_total_cuenta(db, usuario_id, cuenta_id):
    estado = obtener_estado_financiero_cuenta(db, usuario_id, cuenta_id)
    if estado is None: raise RuntimeError("Estado financiero no disponible")
    return Decimal(estado["reserva_total_cuenta"] or 0)


def calcular_saldo_real_cuenta(db, cuenta):
    estado = obtener_estado_financiero_cuenta(db, cuenta.usuario_id, cuenta.id_cuenta)
    if estado is None or estado["saldo_actual_cuenta"] is None:
        raise RuntimeError("Saldo real no disponible")
    return Decimal(estado["saldo_actual_cuenta"])


def listar_metas(db, usuario_id, estado, cuenta_id, limite, offset):
    filtros = [Meta.usuario_id == usuario_id]
    if estado is not None: filtros.append(Meta.estado_meta == estado)
    if cuenta_id is not None:
        # Cuenta sugerida O cuenta que efectivamente aportó.
        filtros.append((Meta.cuenta_id == cuenta_id) | select(AsignacionMeta.id_asignacion).where(AsignacionMeta.meta_id == Meta.id_meta, AsignacionMeta.cuenta_id == cuenta_id).exists())
    total = db.scalar(select(func.count()).select_from(Meta).where(*filtros)) or 0
    stmt = select(Meta).where(*filtros).order_by(Meta.fecha_creacion_meta.desc(), Meta.id_meta.desc()).limit(limite).offset(offset)
    return list(db.scalars(stmt)), total


def actualizar_meta(db, meta):
    db.add(meta)
    db.flush()


def agregar_asignacion(db, asignacion):
    db.add(asignacion)
    db.flush()


def listar_asignaciones(db, id_meta, tipo_asignacion, limite, offset):
    filtros = [AsignacionMeta.meta_id == id_meta]
    if tipo_asignacion is not None: filtros.append(AsignacionMeta.tipo_asignacion == tipo_asignacion)
    total = db.scalar(select(func.count()).select_from(AsignacionMeta).where(*filtros)) or 0
    stmt = select(AsignacionMeta).where(*filtros).order_by(AsignacionMeta.fecha_registro_asignacion.desc(), AsignacionMeta.id_asignacion.desc()).limit(limite).offset(offset)
    return list(db.scalars(stmt)), total
