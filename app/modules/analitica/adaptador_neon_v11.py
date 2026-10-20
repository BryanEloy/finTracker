"""Adaptador PostgreSQL/Neon V1.1 para FastAPI (psycopg 3, opcional).

No contiene credenciales, no conecta al importarse y no implementa HTTP/JWT.
Cada operación recibe una conexión NUEVA/IDLE, exclusiva de esa operación:
no compartir conexión ni cursor entre hilos o solicitudes. El llamador abre y
cierra la conexión (preferentemente endpoint directo Neon para estas operaciones).
Todas las consultas son parametrizadas. Las FK no sustituyen autenticación.

La carga NO inventa origen REAL/SINTETICO ni cobertura histórica. Ambos requieren
una política de datos del backend; tener transacciones antiguas no prueba que
se registraron todos los días sin gasto. El guardado solo evita INSERT repetidos:
no evita entrenamiento ya ejecutado. Una caché anterior al cómputo es otro paso.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID


MAX_FILAS_COLECCION = 100_000


class ErrorAdaptador(RuntimeError):
    """Fallo de contrato/configuración del adaptador; no exponer trazas al móvil."""


class UsuarioNoDisponible(ErrorAdaptador):
    """Usuario inexistente o desactivado. FastAPI decide el código HTTP público."""


class PeriodoNoEncontrado(ErrorAdaptador):
    """Identificador de periodo inexistente o ajeno (misma respuesta pública)."""


class LimiteDatosExcedido(ErrorAdaptador):
    """Se debe acotar la carga explícitamente; nunca entrenar con truncado oculto."""


class InstantaneaNoCoherente(ErrorAdaptador):
    """Reintentar lectura en una conexión nueva; nunca combinar dos instantáneas."""


def _psycopg():
    try:
        from psycopg.pq import TransactionStatus
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise ErrorAdaptador("Instalar psycopg[binary] versión 3 para usar el adaptador.") from exc
    return TransactionStatus, dict_row, Jsonb


def _uuid(valor: Any, campo: str) -> str:
    try:
        return str(UUID(str(valor)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ErrorAdaptador(f"{campo}: se requiere UUID válido.") from exc


def _conexion_idle(conn):
    TransactionStatus, dict_row, Jsonb = _psycopg()
    if conn.closed or conn.info.transaction_status != TransactionStatus.IDLE:
        raise ErrorAdaptador("Usar una conexión abierta, nueva/IDLE y exclusiva para cada operación.")
    return dict_row, Jsonb


def _tipos_propios(valor):
    """UUID -> str para el motor; conserva Decimal, date y datetime originales."""
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, Mapping):
        return {k: _tipos_propios(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_tipos_propios(v) for v in valor]
    return valor


def _coleccion(cur, sql: str, parametros: tuple, nombre: str):
    cur.execute(sql, (*parametros, MAX_FILAS_COLECCION + 1))
    filas = cur.fetchall()
    if len(filas) > MAX_FILAS_COLECCION:
        raise LimiteDatosExcedido(f"{nombre}: supera {MAX_FILAS_COLECCION} filas; no se truncó el historial.")
    return _tipos_propios(filas)


def _validar_usuario_y_schema(cur, usuario_id: str):
    cur.execute("SELECT es_activo_usuario FROM public.usuario WHERE id_usuario = %s::uuid", (usuario_id,))
    usuario = cur.fetchone()
    if usuario is None or usuario["es_activo_usuario"] is not True:
        raise UsuarioNoDisponible("El usuario no existe o está desactivado.")
    cur.execute("SELECT version FROM public.fintrack_schema_version ORDER BY aplicado_en DESC LIMIT 1")
    version = cur.fetchone()
    if version is None or version["version"] != "1.1":
        raise ErrorAdaptador("La última versión SQL identificada no es FinTrack 1.1.")


def cargar_instantanea(conn, usuario_id, periodo_id=None) -> dict:
    """Carga datos propios de una instantánea REPEATABLE READ READ ONLY.

    Sin periodo_id elige exclusivamente ACTIVO; si no existe, periodo=None y
    detalles=[]. Un ID explícito puede consultar histórico y conserva su fecha
    de cierre. No se elige arbitrariamente el último periodo de otro estado.
    Cada colección está acotada a 100000 filas; exceder provoca error completo.
    Las vistas agregadas SQL son fuente de verdad, no se rehacen con floats.
    """
    uid = _uuid(usuario_id, "usuario_id")
    pid = _uuid(periodo_id, "periodo_id") if periodo_id is not None else None
    dict_row, _ = _conexion_idle(conn)
    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cur.execute("SELECT transaction_timestamp() AS fecha_corte_datos")
            corte = cur.fetchone()["fecha_corte_datos"]
            _validar_usuario_y_schema(cur, uid)
            # Esta guardia cubre la carrera de milisegundos entre BEGIN y la
            # adquisición de snapshot: las vistas agregadas no llevan cutoff.
            # No permitiría devolver agregados que incluyen filas omitidas de
            # las colecciones analíticas. Repetir la operación, no ocultar filas.
            cur.execute("""
                SELECT 1 FROM public.vw_transaccion_periodo_v11
                WHERE usuario_id = %s::uuid AND
                    (fecha_registro_transaccion > %s OR
                     fecha_operacion_transaccion > (%s AT TIME ZONE 'America/Mexico_City')::date)
                LIMIT 1
            """, (uid, corte, corte))
            if cur.fetchone() is not None:
                raise InstantaneaNoCoherente("Hay movimientos posteriores al corte visible; repetir lectura en nueva conexión.")
            movimientos = _coleccion(cur, """
                SELECT id_transaccion, usuario_id, periodo_id, grupo_id,
                       categoria_id, subcategoria_id, fecha_operacion_transaccion,
                       fecha_registro_transaccion, tipo_transaccion, gasto_conocido,
                       aplicado_dinero, ingreso_libre, ingreso_reservado, nueva_deuda
                FROM public.vw_movimiento_analitico_v11
                WHERE usuario_id = %s::uuid
                  AND fecha_registro_transaccion <= %s
                  AND fecha_operacion_transaccion <= (%s AT TIME ZONE 'America/Mexico_City')::date
                ORDER BY fecha_operacion_transaccion, fecha_registro_transaccion, id_transaccion
                LIMIT %s
            """, (uid, corte, corte), "movimientos_analiticos")
            transacciones = _coleccion(cur, """
                SELECT id_transaccion, usuario_id, cuenta_id, tipo_transaccion,
                       cuenta_destino_id, categoria_id, subcategoria_id,
                       monto_transaccion, fecha_registro_transaccion,
                       comentario_transaccion, periodo_id, grupo_id,
                       monto_reduccion_deuda, es_ingreso_reservado,
                       fecha_operacion_transaccion, referencia_transaccion
                FROM public.vw_transaccion_periodo_v11
                WHERE usuario_id = %s::uuid
                  AND fecha_registro_transaccion <= %s
                  AND fecha_operacion_transaccion <= (%s AT TIME ZONE 'America/Mexico_City')::date
                ORDER BY fecha_operacion_transaccion, fecha_registro_transaccion, id_transaccion
                LIMIT %s
            """, (uid, corte, corte), "transacciones")
            grupos = _coleccion(cur, """
                SELECT id_grupo, usuario_id, codigo_grupo, nombre_grupo,
                       naturaleza_grupo, porcentaje_sugerido_grupo, es_activo_grupo
                FROM public.grupo WHERE usuario_id = %s::uuid
                ORDER BY codigo_grupo, id_grupo LIMIT %s
            """, (uid,), "grupos")
            categorias = _coleccion(cur, """
                SELECT id_categoria, usuario_id, grupo_id, nombre_categoria, es_activa_categoria
                FROM public.categoria WHERE usuario_id = %s::uuid
                ORDER BY grupo_id, id_categoria LIMIT %s
            """, (uid,), "categorias")
            subcategorias = _coleccion(cur, """
                SELECT s.id_subcategoria, s.categoria_id, s.nombre_subcategoria,
                       s.es_activa_subcategoria, c.usuario_id
                FROM public.subcategoria s JOIN public.categoria c ON c.id_categoria = s.categoria_id
                WHERE c.usuario_id = %s::uuid
                ORDER BY s.categoria_id, s.id_subcategoria LIMIT %s
            """, (uid,), "subcategorias")
            if pid is None:
                cur.execute("""
                    SELECT * FROM public.vw_periodo_resumen_v11
                    WHERE usuario_id = %s::uuid AND estado_periodo = 'ACTIVO'
                """, (uid,))
            else:
                cur.execute("""
                    SELECT * FROM public.vw_periodo_resumen_v11
                    WHERE usuario_id = %s::uuid AND id_periodo = %s::uuid
                """, (uid, pid))
            periodo = _tipos_propios(cur.fetchone())
            if pid is not None and periodo is None:
                raise PeriodoNoEncontrado("Periodo inexistente o no disponible para este usuario.")
            detalles = []
            intereses = Decimal("0.00")
            if periodo is not None:
                pid_efectivo = periodo["id_periodo"]
                detalles = _coleccion(cur, """
                    SELECT * FROM public.vw_detalle_periodo_grupo_v11
                    WHERE usuario_id = %s::uuid AND periodo_id = %s::uuid
                    ORDER BY codigo_grupo, grupo_id LIMIT %s
                """, (uid, pid_efectivo), "detalles_periodo")
                cur.execute("""
                    SELECT COALESCE(SUM(monto_transaccion - COALESCE(monto_reduccion_deuda, 0)), 0)
                           AS intereses_periodo
                    FROM public.vw_transaccion_periodo_v11
                    WHERE usuario_id = %s::uuid AND periodo_id = %s::uuid
                      AND tipo_transaccion = 'PAGO_DEUDA'
                      AND fecha_registro_transaccion <= %s
                      AND fecha_operacion_transaccion <= (%s AT TIME ZONE 'America/Mexico_City')::date
                """, (uid, pid_efectivo, corte, corte))
                intereses = cur.fetchone()["intereses_periodo"]
    return {"usuario_id": uid, "schema_version": "1.1", "fecha_corte_datos": corte,
            "movimientos_analiticos": movimientos, "transacciones": transacciones,
            "grupos": grupos, "categorias": categorias, "subcategorias": subcategorias,
            "periodo": periodo, "detalles_periodo": detalles,
            "intereses_periodo": intereses}


# 27 columnas en tabla: estas 25 se escriben; ID y fecha de generación son BD.
_COLUMNAS_PREDICCION = (
    "usuario_id", "grupo_id", "periodo_id", "tipo_prediccion", "fecha_corte_datos",
    "periodo_inicio_historial", "periodo_fin_historial", "periodo_inicio_objetivo",
    "periodo_fin_objetivo", "gasto_estimado_prediccion", "rango_min_estimado",
    "rango_max_estimado", "pendiente_tendencia_semanal", "score_salud_difuso",
    "nivel_confiabilidad_ux", "modelo_utilizado", "version_modelo",
    "semanas_completas_utilizadas", "origen_datos", "huella_datos", "mae_modelo",
    "mae_naive_base", "rmse_modelo", "r2_modelo", "metadatos_modelo",
)


def _buscar_cache(cur, registro):
    """Coincidencia estricta de la instantánea; no selecciona solo 'el último'."""
    cur.execute("""
        SELECT id_prediccion FROM public.prediccion
        WHERE usuario_id = %s::uuid AND tipo_prediccion = %s
          AND grupo_id IS NOT DISTINCT FROM %s::uuid
          AND periodo_id IS NOT DISTINCT FROM %s::uuid
          AND origen_datos = %s AND huella_datos = %s AND version_modelo = %s
          AND modelo_utilizado = %s AND fecha_corte_datos = %s
          AND periodo_inicio_historial = %s AND periodo_fin_historial = %s
          AND periodo_inicio_objetivo IS NOT DISTINCT FROM %s::date
          AND periodo_fin_objetivo IS NOT DISTINCT FROM %s::date
        ORDER BY fecha_generacion_prediccion DESC, id_prediccion DESC LIMIT 1
    """, tuple(registro[k] for k in (
        "usuario_id", "tipo_prediccion", "grupo_id", "periodo_id", "origen_datos",
        "huella_datos", "version_modelo", "modelo_utilizado", "fecha_corte_datos",
        "periodo_inicio_historial", "periodo_fin_historial", "periodo_inicio_objetivo",
        "periodo_fin_objetivo")))
    fila = cur.fetchone()
    return UUID(str(fila["id_prediccion"])) if fila else None


def guardar_prediccion(conn, resultado, contexto) -> UUID | None:
    """Reutiliza fila EXACTA o INSERT append-only de un resultado persistible.

    El motor construye el registro condicional y valida finitud/rangos. El SQL
    sigue validando sus restricciones; cualquier error revierte la transacción.
    Nunca modifica saldos ni usa UPDATE/UPSERT. No guarda autoclasificación,
    proyección determinista ni estados insuficientes. El UUID solo se devuelve
    después de COMMIT exitoso. ID/fecha de generación se obtienen de PostgreSQL.
    """
    from fintrack_v1_1_softcomputing_engine import construir_registro_prediccion
    registro = construir_registro_prediccion(resultado, contexto)
    if registro is None:
        return None
    if set(registro) != set(_COLUMNAS_PREDICCION):
        raise ErrorAdaptador("El registro persistible no coincide con las 25 columnas SQL de escritura.")
    uid = _uuid(contexto.usuario_id, "usuario_id")
    if _uuid(registro["usuario_id"], "usuario_id") != uid:
        raise ErrorAdaptador("Registro analítico de otro propietario.")
    if not isinstance(registro["metadatos_modelo"], dict):
        raise ErrorAdaptador("metadatos_modelo debe ser un objeto JSON.")
    dict_row, Jsonb = _conexion_idle(conn)
    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            # Serializa deduplicación e inserción para el mismo usuario; evita
            # depender de una UNIQUE inexistente o un ON CONFLICT indebido.
            cur.execute("SELECT public.fn_usuario_lock_v11(%s::uuid, true)", (uid,))
            _validar_usuario_y_schema(cur, uid)
            identificador = _buscar_cache(cur, registro)
            if identificador is None:
                valores = [registro[c] for c in _COLUMNAS_PREDICCION]
                valores[-1] = Jsonb(registro["metadatos_modelo"], dumps=lambda obj: json.dumps(
                    obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
                # Nombre de columnas y marcadores son constantes internas,
                # nunca proceden de un cuerpo HTTP ni entrada del usuario.
                sql = ("INSERT INTO public.prediccion (" + ", ".join(_COLUMNAS_PREDICCION) +
                       ") VALUES (" + ", ".join(["%s"] * len(_COLUMNAS_PREDICCION)) +
                       ") RETURNING id_prediccion")
                cur.execute(sql, valores)
                identificador = UUID(str(cur.fetchone()["id_prediccion"]))
                cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    return identificador
