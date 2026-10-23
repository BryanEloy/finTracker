
"""Integración de las cuatro rutas analíticas FinTrack V1.1.

Conserva JWT, conexión a Neon, validaciones y algoritmos existentes.
La persistencia de predicciones está desactivada por defecto.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.analitica.adaptador_neon_v11 import (
    ErrorAdaptador,
    InstantaneaNoCoherente,
    LimiteDatosExcedido,
    PeriodoNoEncontrado,
    UsuarioNoDisponible,
    cargar_instantanea,
    guardar_prediccion,
)
from app.modules.analitica.fintrack_v1_1_softcomputing_engine import (
    ContextoAnalitico,
    MotorConCache,
    respuesta_json,
    sugerir_clasificacion_texto,
)


_LOG = logging.getLogger("fintrack.analitica")


class _ErrorPublico(Exception):
    def __init__(self, estado, codigo, mensaje):
        self.estado = estado
        self.codigo = codigo
        self.mensaje = mensaje


def _uuid_publico(valor, nombre):
    try:
        if isinstance(valor, bool) or valor is None:
            raise ValueError()
        return str(UUID(str(valor)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise _ErrorPublico(
            422,
            "FILTRO_INVALIDO",
            f"{nombre} debe ser UUID válido.",
        ) from exc


def _respuesta_error(estado, codigo, mensaje):
    return JSONResponse(
        status_code=estado,
        content={
            "error": {
                "codigo": codigo,
                "mensaje": mensaje,
            }
        },
    )


def crear_router(
    obtener_usuario_activo,
    conexion_factory,
    politica_datos,
    *,
    persistir_resultados=False,
):
    """Construye el router una sola vez al iniciar FastAPI."""

    if not all(
        callable(funcion)
        for funcion in (
            obtener_usuario_activo,
            conexion_factory,
            politica_datos,
        )
    ):
        raise TypeError(
            "Se requieren tres funciones de integración del backend."
        )

    if not isinstance(persistir_resultados, bool):
        raise TypeError(
            "persistir_resultados debe ser booleano de configuración."
        )

    motor = MotorConCache(max_entradas=32)
    concurrencia = asyncio.Semaphore(2)

    router = APIRouter(
        prefix="/api/v1/analitica",
        tags=["Analítica FinTrack V1.1"],
    )

    def _instantanea(uid, periodo_id):
        conn = conexion_factory()

        try:
            return cargar_instantanea(
                conn,
                uid,
                periodo_id=periodo_id,
            )
        finally:
            conn.close()

    def _persistir_si_nuevo(resultado, contexto):
        if (
            not persistir_resultados
            or resultado.get("estado") != "OK"
            or resultado.get(
                "cache_precomputo", {}
            ).get("reutilizado") is True
        ):
            return

        conn = None

        try:
            conn = conexion_factory()

            guardar_prediccion(
                conn,
                resultado,
                contexto,
            )

        except Exception:
            motor.limpiar()
            raise

        finally:
            if conn is not None:
                conn.close()

    def _operacion(uid, accion, parametros):
        snapshot = _instantanea(
            uid,
            parametros.get("periodo_id"),
        )

        politica = politica_datos(uid, snapshot)

        if (
            not isinstance(politica, Mapping)
            or not {
                "origen_datos",
                "cobertura",
            }.issubset(politica)
        ):
            raise ErrorAdaptador(
                "Falta política explícita de origen y cobertura del backend."
            )

        from datetime import timedelta

        fecha_corte = snapshot["fecha_corte_datos"]

        contexto = ContextoAnalitico(
            usuario_id=uid,
            fecha_corte_datos=fecha_corte,
            origen_datos=politica["origen_datos"],
            fecha_generacion=max(
                datetime.now(timezone.utc),
                fecha_corte,
            ),
        )

        if accion == "pronostico":
            gid = parametros.get("grupo_id")

            if gid is not None:
                grupos = [
                    g
                    for g in snapshot["grupos"]
                    if (
                        str(g["id_grupo"]) == gid
                        and str(g["usuario_id"]) == uid
                    )
                ]

                if not grupos:
                    raise _ErrorPublico(
                        404,
                        "GRUPO_NO_ENCONTRADO",
                        "Grupo no encontrado.",
                    )

                if grupos[0]["codigo_grupo"] not in (
                    "G002",
                    "G003",
                ):
                    raise _ErrorPublico(
                        422,
                        "GRUPO_NO_ADMITIDO",
                        "El pronóstico por grupo admite únicamente Gastos fijos o Gustos.",
                    )

            resultado = motor.pronostico(
                snapshot["movimientos_analiticos"],
                contexto,
                cobertura=politica["cobertura"],
                grupo_id=gid,
                grupos=snapshot["grupos"],
                forzar=parametros.get("forzar", False),
            )

            if resultado.get("estado") == "MODELO_NO_DISPONIBLE":
                raise _ErrorPublico(
                    503,
                    "MODELO_NO_DISPONIBLE",
                    "El modelo no pudo producir un ajuste estable; intenta más tarde.",
                )

            _persistir_si_nuevo(resultado, contexto)

        elif accion == "clustering":
            resultado = motor.clustering(
                snapshot["transacciones"],
                contexto,
                periodo=snapshot["periodo"],
            )

            _persistir_si_nuevo(resultado, contexto)

        elif accion == "salud":
            periodo = dict(snapshot["periodo"])

            periodo["intereses_periodo"] = (
                snapshot["intereses_periodo"]
            )

            pronostico = motor.pronostico(
                snapshot["movimientos_analiticos"],
                contexto,
                cobertura=politica["cobertura"],
                grupos=snapshot["grupos"],
            )

            resultado = motor.salud(
                periodo,
                snapshot["detalles_periodo"],
                contexto,
                pronostico=pronostico,
            )

            _persistir_si_nuevo(pronostico, contexto)
            _persistir_si_nuevo(resultado, contexto)

        else:
            resultado = sugerir_clasificacion_texto(
                parametros["detalle"],
                snapshot["transacciones"],
                snapshot["categorias"],
                snapshot["subcategorias"],
                snapshot["grupos"],
                contexto,
            )

        return respuesta_json(resultado)

    async def _servir(
        request,
        uid,
        accion,
        permitidos,
        **parametros,
    ):
        try:
            try:
                uid = str(UUID(str(uid)))

            except (
                ValueError,
                TypeError,
                AttributeError,
            ) as exc:
                raise ErrorAdaptador(
                    "La dependencia debe retornar el UUID propio."
                ) from exc

            nombres = [
                nombre
                for nombre, _ in request.query_params.multi_items()
            ]

            if (
                set(nombres) - set(permitidos)
                or len(nombres) != len(set(nombres))
            ):
                raise _ErrorPublico(
                    422,
                    "PARAMETROS_NO_ADMITIDOS",
                    "Hay parámetros adicionales o repetidos.",
                )

            if await request.body():
                raise _ErrorPublico(
                    422,
                    "BODY_NO_ADMITIDO",
                    "Esta consulta GET no admite cuerpo.",
                )

            if accion == "pronostico":
                gid = request.query_params.get("grupo_id")

                parametros["grupo_id"] = (
                    _uuid_publico(gid, "grupo_id")
                    if gid is not None
                    else None
                )

                forzar = request.query_params.get(
                    "forzar_recalculo",
                    "false",
                ).lower()

                if forzar not in ("true", "false"):
                    raise _ErrorPublico(
                        422,
                        "FILTRO_INVALIDO",
                        "forzar_recalculo debe ser true o false.",
                    )

                parametros["forzar"] = forzar == "true"

            elif accion == "clustering":
                pid = request.query_params.get("periodo_id")

                parametros["periodo_id"] = (
                    _uuid_publico(pid, "periodo_id")
                    if pid is not None
                    else None
                )

            elif accion == "salud":
                parametros["periodo_id"] = _uuid_publico(
                    parametros["periodo_id"],
                    "id_periodo",
                )

            else:
                detalle = request.query_params.get(
                    "detalle",
                    "",
                ).strip()

                if not 3 <= len(detalle) <= 500:
                    raise _ErrorPublico(
                        422,
                        "DETALLE_VACIO_O_INVALIDO",
                        "detalle debe contener entre 3 y 500 caracteres.",
                    )

                parametros["detalle"] = detalle

            async with concurrencia:
                return await run_in_threadpool(
                    _operacion,
                    uid,
                    accion,
                    parametros,
                )

        except _ErrorPublico as exc:
            return _respuesta_error(
                exc.estado,
                exc.codigo,
                exc.mensaje,
            )

        except UsuarioNoDisponible:
            return _respuesta_error(
                403,
                "USUARIO_DESACTIVADO",
                "El usuario no está disponible para esta operación.",
            )

        except PeriodoNoEncontrado:
            return _respuesta_error(
                404,
                "PERIODO_NO_ENCONTRADO",
                "Periodo no encontrado.",
            )

        except (
            LimiteDatosExcedido,
            InstantaneaNoCoherente,
        ):
            return _respuesta_error(
                503,
                "INSTANTANEA_NO_DISPONIBLE",
                "No se pudo preparar una instantánea completa; intenta más tarde.",
            )

        except ErrorAdaptador:
            _LOG.warning(
                "Integración analítica no disponible; revisar configuración del backend."
            )

            return _respuesta_error(
                503,
                "ERROR_SERVICIO",
                "El servicio analítico no está disponible temporalmente.",
            )

        except Exception as exc:
            # Diagnóstico opt-in SOLO para desarrollo local. Nunca incluir
            # detalles internos de la excepción en la respuesta HTTP.
            if os.getenv("FINTRACK_ANALITICA_DEBUG", "0") == "1":
                logging.getLogger("uvicorn.error").exception(
                    "Error interno de analítica (depuración local)"
                )
                return _respuesta_error(
                    500,
                    "ERROR_ANALITICA",
                    "No se pudo completar el análisis; intenta más tarde.",
                )
            else:
                _LOG.warning(
                    "Fallo analítico de tipo %s",
                    type(exc).__name__,
                )

            return _respuesta_error(
                500,
                "ERROR_ANALITICA",
                "No se pudo completar el análisis; intenta más tarde.",
            )

    # -----------------------------------------
    # ENDPOINT 1: PREDICCIÓN SEMANAL
    # -----------------------------------------

    @router.get("/prediccion-semanal")
    async def prediccion_semanal(
        request: Request,
        grupo_id: str | None = Query(
            None,
            description="UUID del grupo G002 o G003 (opcional)",
        ),
        forzar_recalculo: str = Query(
            "false",
            description="true o false",
        ),
        usuario_id=Depends(obtener_usuario_activo),
    ):
        return await _servir(
            request,
            usuario_id,
            "pronostico",
            {"grupo_id", "forzar_recalculo"},
        )

    # -----------------------------------------
    # ENDPOINT 2: CLUSTERING K-MEANS
    # -----------------------------------------

    @router.get("/clustering-gastos")
    async def clustering_gastos(
        request: Request,
        periodo_id: str | None = Query(
            None,
            description="UUID de un periodo propio; omitido usa ACTIVO",
        ),
        usuario_id=Depends(obtener_usuario_activo),
    ):
        return await _servir(
            request,
            usuario_id,
            "clustering",
            {"periodo_id"},
        )

    # -----------------------------------------
    # ENDPOINT 3: SALUD FINANCIERA MAMDANI
    # -----------------------------------------

    @router.get("/salud-periodo/{id_periodo}")
    async def salud_periodo(
        id_periodo: str,
        request: Request,
        usuario_id=Depends(obtener_usuario_activo),
    ):
        return await _servir(
            request,
            usuario_id,
            "salud",
            set(),
            periodo_id=id_periodo,
        )

    # -----------------------------------------
    # ENDPOINT 4: CLASIFICACIÓN INTELIGENTE
    # -----------------------------------------

    @router.get("/sugerir-clasificacion")
    async def sugerir_clasificacion(
        request: Request,
        detalle: str | None = Query(
            None,
            description="Descripción del gasto, de 3 a 500 caracteres",
        ),
        usuario_id=Depends(obtener_usuario_activo),
    ):
        return await _servir(
            request,
            usuario_id,
            "clasificacion",
            {"detalle"},
        )

    return router
