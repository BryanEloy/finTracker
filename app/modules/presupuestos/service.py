from uuid import UUID
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from app.modules.presupuestos import repository as repo

class PresupuestoError(Exception):
    def __init__(self, mensaje, codigo=422):
        self.mensaje, self.codigo = mensaje, codigo
        super().__init__(mensaje)

def traducir_error(exc):
    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None)
    constraint = getattr(getattr(original, "diag", None), "constraint_name", None)
    if sqlstate == "23505": return PresupuestoError("Ya existe un registro incompatible o un período activo",409)
    if sqlstate == "23503": return PresupuestoError("Un grupo o período relacionado no pertenece al usuario o no existe",422)
    if constraint == "ck_v11_periodo_distribucion_completa": return PresupuestoError("Se requieren cuatro grupos y porcentajes que sumen 100",422)
    if sqlstate in ("23514", "55000"): return PresupuestoError("Neon rechazó la operación por una regla del período: " + str(original).split("\n")[0],422)
    return PresupuestoError("Error de integridad al guardar el presupuesto",422)

def detalle(db, uid, pid):
    base = repo.obtener(db,uid,pid)
    if base is None: raise PresupuestoError("PERIODO_NO_ENCONTRADO",404)
    return {"periodo":base,"grupos":repo.detalles(db,uid,pid)}

def listar(db, uid):
    return {"presupuestos":repo.listar(db,uid)}

def crear(db, uid, datos):
    try:
        repo.lock_usuario(db,uid)
        activos = repo.grupos_usuario(db,uid)
        if {g.grupo_id for g in datos.grupos} != activos or len(activos)!=4:
            raise PresupuestoError("Debe usar exactamente los cuatro grupos activos de su usuario",422)
        pid=repo.insertar_periodo(db,uid,datos)
        for g in datos.grupos: repo.insertar_grupo(db,uid,pid,g)
        db.commit()  # Los triggers DEFERRABLE se comprueban aquí
    except PresupuestoError:
        db.rollback(); raise
    except (DBAPIError,IntegrityError) as exc:
        db.rollback(); raise traducir_error(exc) from exc
    return detalle(db,uid,pid)

def editar(db,uid,pid,datos):
    actual=detalle(db,uid,pid)
    if actual["periodo"]["estado_periodo"]!="ACTIVO": raise PresupuestoError("PERIODO_CERRADO",409)
    try:
        repo.lock_usuario(db,uid)
        repo.actualizar(db,uid,pid,datos.model_dump(exclude_none=True))
        db.commit()
    except DBAPIError as exc:
        db.rollback(); raise traducir_error(exc) from exc
    return detalle(db,uid,pid)

def distribuir(db,uid,pid,grupos):
    actual=detalle(db,uid,pid)
    if actual["periodo"]["estado_periodo"]!="ACTIVO": raise PresupuestoError("PERIODO_CERRADO",409)
    if len(grupos)!=4 or len({g.grupo_id for g in grupos})!=4 or sum(g.porcentaje_asignado_grupo for g in grupos)!=100:
        raise PresupuestoError("Se requieren cuatro grupos distintos que sumen 100",422)
    existentes={g["grupo_id"] for g in actual["grupos"]}
    if {g.grupo_id for g in grupos}!=existentes: raise PresupuestoError("Debe actualizar los cuatro grupos del período",422)
    try:
        repo.lock_usuario(db,uid)
        repo.actualizar_distribucion(db,uid,pid,{g.grupo_id:g.porcentaje_asignado_grupo for g in grupos})
        db.commit()
    except DBAPIError as exc:
        db.rollback(); raise traducir_error(exc) from exc
    return detalle(db,uid,pid)

def cerrar(db,uid,pid,estado):
    actual=detalle(db,uid,pid)
    if actual["periodo"]["estado_periodo"]!="ACTIVO": raise PresupuestoError("PERIODO_CERRADO",409)
    try:
        repo.lock_usuario(db,uid)
        repo.cerrar(db,uid,pid,estado)
        db.commit()
    except DBAPIError as exc:
        db.rollback(); raise traducir_error(exc) from exc
    return detalle(db,uid,pid)
