"""Consultas para la futura APK: periodos, cortes y desglose sin modificar SQL.

Usa las vistas y la función de corte ya existentes en la migración V1.1. No
actualiza transacciones para asignarles periodo, no crea vistas ni escribe datos.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from enum import Enum
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.analitica.fintrack_v1_1_softcomputing_engine import moneda, respuesta_json


_LOG = logging.getLogger("fintrack.reportes")
_CABECERAS = {"Cache-Control": "private, no-store, max-age=0", "Pragma": "no-cache"}


class TipoMovimiento(str, Enum):
    INGRESO = "INGRESO"
    INGRESO_RESERVADO = "INGRESO_RESERVADO"
    GASTO = "GASTO"
    TRANSFERENCIA = "TRANSFERENCIA"
    PAGO_DEUDA = "PAGO_DEUDA"
    PRESTAMO_RECIBIDO = "PRESTAMO_RECIBIDO"
    ANTICIPO_REEMBOLSABLE = "ANTICIPO_REEMBOLSABLE"
    REEMBOLSO = "REEMBOLSO"
    DEVOLUCION_GASTO = "DEVOLUCION_GASTO"


class _ErrorReporte(Exception):
    def __init__(self, estado, codigo, mensaje):
        self.estado, self.codigo, self.mensaje = estado, codigo, mensaje


def _error(estado, codigo, mensaje):
    return JSONResponse(status_code=estado, headers=_CABECERAS,
                        content={"error": {"codigo": codigo, "mensaje": mensaje}})


def _periodo(cur, uid, pid):
    cur.execute("""SELECT id_periodo, usuario_id, codigo_periodo, tipo_periodo,
                          fecha_inicio_periodo, fecha_fin_periodo, estado_periodo
                   FROM public.periodo
                   WHERE usuario_id = %(uid)s AND id_periodo = %(pid)s""",
                {"uid": uid, "pid": pid})
    fila = cur.fetchone()
    if fila is None:
        raise _ErrorReporte(404, "PERIODO_NO_ENCONTRADO", "Periodo no encontrado.")
    return fila


def _validar_filtros_propios(cur, uid, filtros):
    """Los catálogos inactivos siguen siendo válidos al consultar el historial."""
    for clave, tabla, columna in (("grupo_id", "grupo", "id_grupo"),
                                  ("categoria_id", "categoria", "id_categoria"),
                                  ("cuenta_id", "cuenta", "id_cuenta")):
        valor = filtros.get(clave)
        if valor is not None:
            # Identificadores de SQL elegidos exclusivamente de esta tupla fija.
            cur.execute(f"SELECT {columna} FROM public.{tabla} "
                        f"WHERE usuario_id = %s AND {columna} = %s", (uid, valor))
            if cur.fetchone() is None:
                raise _ErrorReporte(404, "FILTRO_NO_ENCONTRADO", "Filtro no encontrado.")
    sid = filtros.get("subcategoria_id")
    if sid is not None:
        cur.execute("""SELECT s.categoria_id FROM public.subcategoria s
                       JOIN public.categoria c ON c.id_categoria = s.categoria_id
                       WHERE c.usuario_id = %s AND s.id_subcategoria = %s""", (uid, sid))
        sub = cur.fetchone()
        if sub is None:
            raise _ErrorReporte(404, "FILTRO_NO_ENCONTRADO", "Filtro no encontrado.")
        if filtros.get("categoria_id") is not None and sub["categoria_id"] != filtros["categoria_id"]:
            raise _ErrorReporte(422, "FILTROS_INCOMPATIBLES",
                                "La subcategoría no corresponde a la categoría seleccionada.")


def _listar_transacciones(cur, uid, corte, filtros):
    pid = filtros.get("periodo_id")
    if filtros["sin_periodo"] and pid is not None:
        raise _ErrorReporte(422, "FILTROS_INCOMPATIBLES",
                            "Selecciona un periodo o Sin periodo, no ambos.")
    if pid is not None:
        _periodo(cur, uid, pid)
    _validar_filtros_propios(cur, uid, filtros)
    params = {"uid": uid, "corte": corte, "limite": filtros["limite"], "offset": filtros["offset"]}
    condiciones = ["t.usuario_id = %(uid)s", "t.fecha_registro_transaccion <= %(corte)s",
                   "t.fecha_operacion_transaccion <= (%(corte)s AT TIME ZONE 'America/Mexico_City')::date"]
    if pid is not None:
        condiciones.append("t.periodo_id = %(pid)s")
        params["pid"] = pid
    elif filtros["sin_periodo"]:
        condiciones.append("t.periodo_id IS NULL")
    if filtros.get("tipo_transaccion") is not None:
        condiciones.append("t.tipo_transaccion::text = %(tipo)s")
        tipo = filtros["tipo_transaccion"]
        params["tipo"] = tipo.value if isinstance(tipo, TipoMovimiento) else str(tipo)
    if filtros.get("cuenta_id") is not None:
        condiciones.append("(t.cuenta_id = %(cuenta)s OR t.cuenta_destino_id = %(cuenta)s)")
        params["cuenta"] = filtros["cuenta_id"]
    donde = " AND ".join(condiciones)  # Solo fragmentos constantes; valores parametrizados.
    fuente = " FROM public.vw_transaccion_periodo_v11 t WHERE " + donde
    cur.execute("SELECT count(*) AS total" + fuente, params)
    total = int(cur.fetchone()["total"])
    cur.execute("""SELECT t.id_transaccion, t.cuenta_id, t.tipo_transaccion,
                          t.cuenta_destino_id, t.categoria_id, t.subcategoria_id,
                          t.monto_transaccion, t.monto_reduccion_deuda,
                          t.fecha_registro_transaccion, t.fecha_operacion_transaccion,
                          t.comentario_transaccion, t.referencia_transaccion,
                          t.periodo_id, t.grupo_id, t.es_ingreso_reservado""" + fuente +
                " ORDER BY t.fecha_operacion_transaccion DESC, t.fecha_registro_transaccion DESC, "
                "t.id_transaccion DESC LIMIT %(limite)s OFFSET %(offset)s", params)
    return {"transacciones": cur.fetchall(), "total": total,
            "limite": filtros["limite"], "offset": filtros["offset"],
            "fecha_corte_datos": corte,
            "criterio_periodo": "Periodo efectivo de vw_transaccion_periodo_v11"}


def _cortes_cuentas(cur, uid, corte, pid):
    periodo = _periodo(cur, uid, pid)  # Autorizar ANTES de llamar la función SQL.
    cur.execute("SELECT * FROM public.fn_corte_cuentas_por_periodo(%s)", (pid,))
    return {"periodo": periodo, "fecha_corte_datos": corte, "cuentas": cur.fetchall(),
            "nota": "Corte histórico del periodo; no es el saldo actual ni una reserva histórica de metas. "
                    "El saldo de alta se informa aparte y no constituye ingreso."}


def _metricas():
    return {"gasto_conocido": Decimal("0"), "aplicado_dinero": Decimal("0"),
            "conteo_movimientos": 0, "conteo_gastos": 0}


def _sumar(nodo, fila):
    for clave in ("gasto_conocido", "aplicado_dinero"):
        nodo[clave] += Decimal(str(fila[clave]))
    for clave in ("conteo_movimientos", "conteo_gastos"):
        nodo[clave] += int(fila[clave])


def _cerrar_nodo(nodo):
    """Importes decimales como texto y estructuras sin referencias compartidas."""
    nodo["gasto_conocido"] = moneda(nodo["gasto_conocido"])
    nodo["aplicado_dinero"] = moneda(nodo["aplicado_dinero"])
    return nodo


def _desglose_gastos(cur, uid, corte, pid, filtros):
    periodo = _periodo(cur, uid, pid)
    _validar_filtros_propios(cur, uid, filtros)
    params = {"uid": uid, "pid": pid, "corte": corte}
    condiciones = ["m.usuario_id = %(uid)s", "m.periodo_id = %(pid)s",
                   "m.fecha_registro_transaccion <= %(corte)s",
                   "m.fecha_operacion_transaccion <= (%(corte)s AT TIME ZONE 'America/Mexico_City')::date",
                   "(m.gasto_conocido <> 0 OR m.aplicado_dinero <> 0)"]
    for clave in ("grupo_id", "categoria_id", "subcategoria_id"):
        if filtros.get(clave) is not None:
            condiciones.append(f"m.{clave} = %({clave})s")
            params[clave] = filtros[clave]
    cur.execute("""SELECT id_grupo, codigo_grupo, nombre_grupo FROM public.grupo
                   WHERE usuario_id = %(uid)s
                   ORDER BY codigo_grupo, id_grupo""", params)
    grupos = {}
    for fila in cur.fetchall():
        if filtros.get("grupo_id") is None or fila["id_grupo"] == filtros["grupo_id"]:
            grupos[fila["id_grupo"]] = {**fila, **_metricas(), "categorias": {}}

    cur.execute("""SELECT m.grupo_id, g.codigo_grupo, g.nombre_grupo,
                          m.categoria_id, c.nombre_categoria,
                          m.subcategoria_id, s.nombre_subcategoria,
                          SUM(m.gasto_conocido) AS gasto_conocido,
                          SUM(m.aplicado_dinero) AS aplicado_dinero,
                          COUNT(*) AS conteo_movimientos,
                          COUNT(*) FILTER (WHERE m.tipo_transaccion = 'GASTO') AS conteo_gastos
                   FROM public.vw_movimiento_analitico_v11 m
                   LEFT JOIN public.grupo g ON g.id_grupo = m.grupo_id AND g.usuario_id = m.usuario_id
                   LEFT JOIN public.categoria c ON c.id_categoria = m.categoria_id AND c.usuario_id = m.usuario_id
                   LEFT JOIN public.subcategoria s ON s.id_subcategoria = m.subcategoria_id
                        AND s.categoria_id = m.categoria_id
                   WHERE """ + " AND ".join(condiciones) + """
                   GROUP BY m.grupo_id, g.codigo_grupo, g.nombre_grupo,
                            m.categoria_id, c.nombre_categoria, m.subcategoria_id, s.nombre_subcategoria
                   ORDER BY g.codigo_grupo NULLS LAST, m.grupo_id, c.nombre_categoria NULLS LAST,
                            m.categoria_id, s.nombre_subcategoria NULLS LAST, m.subcategoria_id""", params)
    totales = _metricas()
    for fila in cur.fetchall():
        gid, cid, sid = fila["grupo_id"], fila["categoria_id"], fila["subcategoria_id"]
        if gid not in grupos:
            grupos[gid] = {"id_grupo": gid, "codigo_grupo": fila["codigo_grupo"],
                           "nombre_grupo": fila["nombre_grupo"] or "Sin grupo", **_metricas(), "categorias": {}}
        grupo = grupos[gid]
        if cid not in grupo["categorias"]:
            grupo["categorias"][cid] = {"categoria_id": cid,
                                        "nombre_categoria": fila["nombre_categoria"] or "Sin categoría",
                                        **_metricas(), "subcategorias": {}}
        categoria = grupo["categorias"][cid]
        if sid not in categoria["subcategorias"]:
            categoria["subcategorias"][sid] = {"subcategoria_id": sid,
                                               "nombre_subcategoria": fila["nombre_subcategoria"] or "Sin subcategoría",
                                               **_metricas()}
        for nodo in (totales, grupo, categoria, categoria["subcategorias"][sid]):
            _sumar(nodo, fila)
    arbol = []
    for grupo in grupos.values():
        categorias = []
        for categoria in grupo["categorias"].values():
            categoria["subcategorias"] = [_cerrar_nodo(sub) for sub in categoria["subcategorias"].values()]
            categorias.append(_cerrar_nodo(categoria))
        grupo["categorias"] = categorias
        arbol.append(_cerrar_nodo(grupo))
    return {"periodo": periodo, "fecha_corte_datos": corte,
            "totales": _cerrar_nodo(totales), "grupos": arbol,
            "nota": "Importes netos: devoluciones restan. Gasto conocido y dinero aplicado son medidas diferentes; "
                    "un pago de capital o ahorro aplicado no se convierte en gasto personal. "
                    "Las operaciones sin categoría se mantienen visibles. Los conteos corresponden a movimientos con efecto financiero."}


def crear_router_reportes(obtener_usuario_activo, conexion_factory):
    """Ambas dependencias son del backend confiable; nunca del teléfono."""
    if not callable(obtener_usuario_activo) or not callable(conexion_factory):
        raise TypeError("Se requieren dependencia JWT activa y fábrica de conexión exclusiva")
    router = APIRouter(prefix="/api/v1/reportes", tags=["Reportes de periodos V1.1"])
    concurrencia = asyncio.Semaphore(2)

    def _consultar(uid, accion, filtros):
        conn = conexion_factory()
        try:
            with conn.transaction():
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    cur.execute("SELECT transaction_timestamp() AS fecha_corte_datos")
                    corte = cur.fetchone()["fecha_corte_datos"]
                    if accion == "transacciones":
                        return _listar_transacciones(cur, uid, corte, filtros)
                    if accion == "cuentas":
                        return _cortes_cuentas(cur, uid, corte, filtros["periodo_id"])
                    return _desglose_gastos(cur, uid, corte, filtros["periodo_id"], filtros)
        finally:
            conn.close()

    async def _servir(request, usuario_id, accion, permitidos, filtros):
        try:
            try:
                uid = UUID(str(usuario_id))
            except (ValueError, TypeError, AttributeError) as exc:
                raise _ErrorReporte(503, "ERROR_SERVICIO", "Identidad no disponible.") from exc
            nombres = [nombre for nombre, _ in request.query_params.multi_items()]
            if set(nombres) - permitidos or len(nombres) != len(set(nombres)):
                raise _ErrorReporte(422, "PARAMETROS_NO_ADMITIDOS", "Hay parámetros adicionales o repetidos.")
            async for fragmento in request.stream():
                if fragmento:
                    raise _ErrorReporte(422, "BODY_NO_ADMITIDO", "Esta consulta GET no admite cuerpo.")
            if "sin_periodo" in request.query_params and request.query_params["sin_periodo"].lower() not in ("true", "false"):
                raise _ErrorReporte(422, "FILTRO_INVALIDO", "sin_periodo debe ser true o false.")
            async with concurrencia:
                resultado = await run_in_threadpool(_consultar, uid, accion, filtros)
            return JSONResponse(content=respuesta_json(resultado), headers=_CABECERAS)
        except _ErrorReporte as exc:
            return _error(exc.estado, exc.codigo, exc.mensaje)
        except psycopg.Error as exc:
            _LOG.warning("Consulta de reportes no disponible: %s", type(exc).__name__)
            return _error(503, "REPORTE_NO_DISPONIBLE", "No se pudo consultar el reporte; intenta más tarde.")
        except Exception as exc:
            _LOG.warning("Fallo de reporte: %s", type(exc).__name__)
            return _error(500, "ERROR_REPORTE", "No se pudo completar la consulta.")

    @router.get("/transacciones")
    async def transacciones(request: Request, periodo_id: UUID | None = None,
                            sin_periodo: bool = False, tipo_transaccion: TipoMovimiento | None = None,
                            cuenta_id: UUID | None = None,
                            limite: int = Query(20, ge=1, le=100),
                            offset: int = Query(0, ge=0, le=1_000_000),
                            usuario_id=Depends(obtener_usuario_activo)):
        return await _servir(request, usuario_id, "transacciones",
                             {"periodo_id", "sin_periodo", "tipo_transaccion", "cuenta_id", "limite", "offset"},
                             {"periodo_id": periodo_id, "sin_periodo": sin_periodo,
                              "tipo_transaccion": tipo_transaccion, "cuenta_id": cuenta_id,
                              "limite": limite, "offset": offset})

    @router.get("/periodos/{periodo_id}/cuentas")
    async def cuentas(periodo_id: UUID, request: Request,
                      usuario_id=Depends(obtener_usuario_activo)):
        return await _servir(request, usuario_id, "cuentas", set(), {"periodo_id": periodo_id})

    @router.get("/periodos/{periodo_id}/gastos")
    async def gastos(periodo_id: UUID, request: Request,
                     grupo_id: UUID | None = None, categoria_id: UUID | None = None,
                     subcategoria_id: UUID | None = None,
                     usuario_id=Depends(obtener_usuario_activo)):
        return await _servir(request, usuario_id, "gastos", {"grupo_id", "categoria_id", "subcategoria_id"},
                             {"periodo_id": periodo_id, "grupo_id": grupo_id,
                              "categoria_id": categoria_id, "subcategoria_id": subcategoria_id})

    return router


__all__ = ["crear_router_reportes", "TipoMovimiento"]
