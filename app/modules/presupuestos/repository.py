"""SQL parametrizado: Neon es fuente de verdad para triggers y vistas."""
from sqlalchemy import text
from sqlalchemy.orm import Session

BASE = "SELECT * FROM public.vw_periodo_resumen_v11 WHERE usuario_id=:uid"
DETALLE = "SELECT * FROM public.vw_detalle_periodo_grupo_v11 WHERE usuario_id=:uid AND periodo_id=:pid ORDER BY codigo_grupo"

def filas(db, sql, params):
    return [dict(r) for r in db.execute(text(sql), params).mappings().all()]

def uno(db, sql, params):
    r = db.execute(text(sql), params).mappings().first()
    return dict(r) if r else None

def listar(db, uid):
    return filas(db, BASE + " ORDER BY fecha_inicio_periodo DESC, id_periodo DESC", {"uid":uid})

def obtener(db, uid, pid):
    return uno(db, BASE + " AND id_periodo=:pid", {"uid":uid,"pid":pid})

def detalles(db, uid, pid):
    return filas(db, DETALLE, {"uid":uid,"pid":pid})

def grupos_usuario(db, uid):
    return {r[0] for r in db.execute(text("SELECT id_grupo FROM public.grupo WHERE usuario_id=:uid AND es_activo_grupo=true"), {"uid":uid}).all()}

def lock_usuario(db, uid):
    db.execute(text("SELECT public.fn_usuario_lock_v11(:uid, TRUE)"), {"uid":uid})

def insertar_periodo(db, uid, datos):
    return db.execute(text("""
        INSERT INTO public.periodo (usuario_id,codigo_periodo,tipo_periodo,
            periodo_anterior_id,fecha_inicio_periodo,fecha_fin_periodo,monto_total_presupuesto)
        VALUES (:uid,:codigo,CAST(:tipo AS public.tipo_periodo_enum),:anterior,:inicio,:fin,:monto)
        RETURNING id_periodo
    """), {"uid":uid,"codigo":datos.codigo_periodo.strip(),"tipo":datos.tipo_periodo,
        "anterior":datos.periodo_anterior_id,"inicio":datos.fecha_inicio_periodo,
        "fin":datos.fecha_fin_periodo,"monto":datos.monto_total_presupuesto}).scalar_one()

def insertar_grupo(db, uid, pid, grupo):
    db.execute(text("""
        INSERT INTO public.detalle_periodo_grupo
            (periodo_id,usuario_id,grupo_id,porcentaje_asignado_grupo,porcentaje_alerta_grupo)
        VALUES (:pid,:uid,:gid,:pct,:alerta)
    """), {"pid":pid,"uid":uid,"gid":grupo.grupo_id,
        "pct":grupo.porcentaje_asignado_grupo,"alerta":grupo.porcentaje_alerta_grupo})

def actualizar(db, uid, pid, cambios):
    if "fecha_fin_periodo" in cambios:
        db.execute(text("UPDATE public.periodo SET fecha_fin_periodo=:fin WHERE id_periodo=:pid AND usuario_id=:uid AND estado_periodo='ACTIVO'"),
                   {"fin":cambios["fecha_fin_periodo"],"pid":pid,"uid":uid})
    if "monto_total_presupuesto" in cambios:
        db.execute(text("UPDATE public.periodo SET monto_total_presupuesto=:monto WHERE id_periodo=:pid AND usuario_id=:uid AND estado_periodo='ACTIVO'"),
                   {"monto":cambios["monto_total_presupuesto"],"pid":pid,"uid":uid})

def actualizar_distribucion(db, uid, pid, asignaciones):
    for gid, pct in asignaciones.items():
        db.execute(text("""
            UPDATE public.detalle_periodo_grupo SET porcentaje_asignado_grupo=:pct
            WHERE usuario_id=:uid AND periodo_id=:pid AND grupo_id=:gid
        """), {"uid":uid,"pid":pid,"gid":gid,"pct":pct})

def cerrar(db, uid, pid, estado):
    db.execute(text("""
        UPDATE public.periodo SET estado_periodo=CAST(:estado AS public.estado_presupuesto_enum)
        WHERE id_periodo=:pid AND usuario_id=:uid AND estado_periodo='ACTIVO'
    """), {"estado":estado,"uid":uid,"pid":pid})
