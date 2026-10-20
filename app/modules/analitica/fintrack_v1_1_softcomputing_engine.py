"""FinTrack V1.1: motor analítico puro, sin conexiones ni escrituras automáticas.

Contrato: SQL V1.1 aplicado y funcionalidades finales del 17-10-2026.
El propietario, la procedencia y la cobertura los obtiene el backend confiable,
nunca el BODY del teléfono. Importar este archivo no crea pools ni conexiones.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
from uuid import UUID
from zoneinfo import ZoneInfo
import json
import math
import re
import unicodedata
import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import HuberRegressor, LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.naive_bayes import MultinomialNB

VERSION_MOTOR = "fintrack-sc-1.1.0"
ZONA_LOCAL = ZoneInfo("America/Mexico_City")
MAX_FILAS = 100_000
MAX_MONTO_SQL = Decimal("9999999999.99")


class DatosInvalidos(ValueError):
    """Entrada interna incompatible; FastAPI debe mapearla sin exponer trazas."""


def normalizar_uuid(valor, nombre="uuid"):
    try:
        if isinstance(valor, bool) or valor is None:
            raise ValueError()
        return str(UUID(str(valor)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DatosInvalidos(f"{nombre}: UUID inválido") from exc


def instante_con_zona(valor, nombre="fecha"):
    if isinstance(valor, pd.Timestamp):
        valor = valor.to_pydatetime()
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DatosInvalidos(f"{nombre}: timestamp inválido") from exc
    if not isinstance(valor, datetime) or valor.tzinfo is None or valor.utcoffset() is None:
        raise DatosInvalidos(f"{nombre}: requiere timestamp con zona horaria")
    return valor.astimezone(timezone.utc)


def fecha_local_valor(valor):
    if isinstance(valor, pd.Timestamp):
        valor = valor.to_pydatetime()
    if isinstance(valor, datetime):
        return valor.astimezone(ZONA_LOCAL).date() if valor.tzinfo is not None else valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            # Las columnas DATE son yyyy-MM-dd; no truncar timestamps silenciosamente.
            return date.fromisoformat(valor)
        except ValueError as exc:
            raise DatosInvalidos("Fecha local inválida; se requiere yyyy-MM-dd") from exc
    raise DatosInvalidos("Se requiere una fecha local DATE")


@dataclass(frozen=True)
class ContextoAnalitico:
    usuario_id: str
    fecha_corte_datos: datetime
    origen_datos: str
    fecha_generacion: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        object.__setattr__(self, "usuario_id", normalizar_uuid(self.usuario_id, "usuario_id"))
        object.__setattr__(self, "fecha_corte_datos", instante_con_zona(self.fecha_corte_datos, "fecha_corte_datos"))
        object.__setattr__(self, "fecha_generacion", instante_con_zona(self.fecha_generacion, "fecha_generacion"))
        if self.origen_datos not in ("REAL", "SINTETICO"):
            raise DatosInvalidos("origen_datos debe ser REAL o SINTETICO, decidido por el backend")
        if self.fecha_corte_datos > self.fecha_generacion:
            raise DatosInvalidos("El corte de datos no puede ser posterior a la generación")

    @property
    def fecha_local(self):
        return self.fecha_corte_datos.astimezone(ZONA_LOCAL).date()


def decimal_finito(valor, nombre="valor", positivo=False):
    if isinstance(valor, (bool, np.bool_)) or valor is None:
        raise DatosInvalidos(f"{nombre}: se requiere un número finito, no booleano/null")
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DatosInvalidos(f"{nombre}: número inválido") from exc
    if not numero.is_finite() or (positivo and numero <= 0):
        raise DatosInvalidos(f"{nombre}: número no finito o no positivo")
    return numero


def moneda(valor):
    numero = decimal_finito(valor)
    try:
        redondeado = numero.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise DatosInvalidos("Importe fuera de la precisión admitida") from exc
    if redondeado == 0:
        redondeado = abs(redondeado)
    return format(redondeado, ".2f")


def registros(datos):
    if datos is None:
        return []
    if isinstance(datos, pd.DataFrame):
        if len(datos) > MAX_FILAS:
            raise DatosInvalidos("Se excedió el límite de filas analíticas")
        return datos.to_dict("records")
    if isinstance(datos, Mapping):
        return [dict(datos)]
    if isinstance(datos, (str, bytes)):
        raise DatosInvalidos("Se requiere una colección de registros")
    salida = []
    for fila in datos:
        if len(salida) >= MAX_FILAS or not isinstance(fila, Mapping):
            raise DatosInvalidos("Colección inválida o demasiado grande")
        salida.append(dict(fila))
    return salida


def filas_propias(datos, contexto, campos=()):
    salida = []
    for fila in registros(datos):
        if "usuario_id" not in fila:
            raise DatosInvalidos("Falta usuario_id en una fuente privada")
        # La selección por propietario precede a cualquier procesamiento de su contenido.
        if normalizar_uuid(fila["usuario_id"], "usuario_id") != contexto.usuario_id:
            continue
        if any(campo not in fila for campo in campos):
            raise DatosInvalidos("La fuente no contiene los campos del contrato SQL")
        if fila.get("fecha_registro_transaccion") is not None:
            if instante_con_zona(fila["fecha_registro_transaccion"], "fecha_registro_transaccion") > contexto.fecha_corte_datos:
                continue
        if fila.get("fecha_operacion_transaccion") is not None:
            if fecha_local_valor(fila["fecha_operacion_transaccion"]) > contexto.fecha_local:
                continue
        # Etiquetas de fixtures/exportaciones no sustituyen al registro confiable del backend.
        if fila.get("origen_datos") is not None and fila["origen_datos"] != contexto.origen_datos:
            raise DatosInvalidos("No se puede mezclar procedencia real y sintética")
        salida.append(fila)
    return salida


def _json_normalizado(valor):
    if isinstance(valor, Decimal):
        return str(decimal_finito(valor))
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, datetime):
        return instante_con_zona(valor).isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, np.generic):
        return _json_normalizado(valor.item())
    if isinstance(valor, Mapping):
        return {str(k): _json_normalizado(v) for k, v in sorted(valor.items(), key=lambda p: str(p[0]))}
    if isinstance(valor, (tuple, list)):
        return [_json_normalizado(v) for v in valor]
    if isinstance(valor, float) and not math.isfinite(valor):
        raise DatosInvalidos("JSON no admite NaN ni infinitos")
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    raise DatosInvalidos(f"Tipo no serializable en JSON: {type(valor).__name__}")


def hash_datos(contexto, tipo, datos, parametros=None):
    normal = _json_normalizado(datos)
    if isinstance(normal, list):
        normal = sorted(normal, key=lambda r: json.dumps(r, ensure_ascii=False, sort_keys=True))
    cuerpo = {"usuario_id": contexto.usuario_id, "origen_datos": contexto.origen_datos,
              "motor": VERSION_MOTOR, "tipo": tipo, "datos": normal,
              "parametros": _json_normalizado(parametros or {})}
    # El corte se añade explícitamente a parámetros si afecta el cálculo (ej. salud).
    # No incluir el reloj de cada consulta permite reconocer el mismo historial semanal.
    return sha256(json.dumps(cuerpo, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def sello_contexto(contexto):
    return hash_datos(contexto, "CONTEXTO", [], {"corte": contexto.fecha_corte_datos.isoformat()})


def base_respuesta(contexto, estado, explicacion, huella=None):
    respuesta = {"estado": estado, "explicacion_ux": explicacion,
                 "origen_datos": contexto.origen_datos, "fecha_corte_datos": contexto.fecha_corte_datos.isoformat(),
                 "fecha_generacion_prediccion": contexto.fecha_generacion.isoformat(),
                 "version_modelo": VERSION_MOTOR, "contexto_analitico": sello_contexto(contexto)}
    if huella is not None:
        respuesta["huella_datos"] = huella
    return respuesta


def respuesta_json(respuesta):
    """Validación final; los montos ya son cadenas y las métricas, números/null."""
    normal = _json_normalizado(respuesta)
    json.dumps(normal, allow_nan=False, ensure_ascii=False)
    return normal



# -----------------------------------------------------------------------------
# Pronóstico semanal: serie de gasto conocido, cobertura explícita y backtesting.
# -----------------------------------------------------------------------------

def _pron_cobertura(intervalos, contexto):
    """Une intervalos inclusivos certificados por backend; no infiere ceros."""
    if isinstance(intervalos, pd.DataFrame):
        intervalos = intervalos.to_dict("records")
    if intervalos is None:
        intervalos = []
    fechas = []
    for intervalo in intervalos:
        if not isinstance(intervalo, dict) and not hasattr(intervalo, "keys"):
            raise DatosInvalidos("Cada intervalo de cobertura debe ser un objeto.")
        if intervalo.get("usuario_id") is not None:
            if normalizar_uuid(intervalo["usuario_id"], "usuario_id") != contexto.usuario_id:
                raise DatosInvalidos("La cobertura debe pertenecer al usuario autenticado.")
        if "fecha_inicio" not in intervalo or "fecha_fin" not in intervalo:
            raise DatosInvalidos("Cobertura requiere fecha_inicio y fecha_fin inclusivas.")
        inicio = fecha_local_valor(intervalo["fecha_inicio"])
        fin = fecha_local_valor(intervalo["fecha_fin"])
        if inicio > fin or fin > contexto.fecha_local:
            raise DatosInvalidos("Intervalo de cobertura invertido o posterior al corte.")
        fechas.append((inicio, fin))
    unidos = []
    for inicio, fin in sorted(fechas):
        if unidos and inicio <= unidos[-1][1] + timedelta(days=1):
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], fin))
        else:
            unidos.append((inicio, fin))
    return unidos


def _pron_grupo_propio(grupo_id, grupos, contexto):
    if grupo_id is None:
        return None
    gid = normalizar_uuid(grupo_id, "grupo_id")
    if isinstance(grupos, pd.DataFrame):
        grupos = grupos.to_dict("records")
    encontrado = None
    for grupo in grupos:
        if normalizar_uuid(grupo.get("usuario_id"), "usuario_id") != contexto.usuario_id:
            continue
        if normalizar_uuid(grupo.get("id_grupo"), "id_grupo") == gid:
            if encontrado is not None:
                raise DatosInvalidos("Grupo duplicado en el catálogo analítico.")
            encontrado = grupo
    if encontrado is None:
        raise DatosInvalidos("GRUPO_NO_ENCONTRADO: debe ser propio y existir.")
    if encontrado.get("codigo_grupo") not in ("G002", "G003"):
        raise DatosInvalidos("GRUPO_NO_ADMITIDO: únicamente G002 o G003.")
    naturaleza = encontrado.get("naturaleza_grupo")
    esperado = {"G002": "GASTOS_FIJOS", "G003": "GUSTOS"}
    if naturaleza is not None and naturaleza != esperado[encontrado["codigo_grupo"]]:
        raise DatosInvalidos("Código y naturaleza del grupo son inconsistentes.")
    return gid


def _pron_fit(nombre, y):
    """Escalado estable; retorna modelo, escala y pendiente en MXN/semana."""
    x = np.arange(len(y), dtype=float)
    x_centro = float(np.mean(x))
    x_escala = max(float(np.std(x)), 1.0)
    y_centro = float(np.median(y))
    y_escala = max(float(np.std(y)), 1.0)
    X = ((x - x_centro) / x_escala).reshape(-1, 1)
    Y = (np.asarray(y, dtype=float) - y_centro) / y_escala
    if nombre == "OLS":
        modelo = LinearRegression()
    else:
        modelo = HuberRegressor(epsilon=1.35, alpha=0.0, max_iter=2000, tol=1e-8)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        modelo.fit(X, Y)
    pendiente = float(modelo.coef_[0]) * y_escala / x_escala
    if not math.isfinite(pendiente):
        raise ValueError("Pendiente no finita.")
    return modelo, x_centro, x_escala, y_centro, y_escala, pendiente


def _pron_predict(ajuste, indice):
    modelo, x_centro, x_escala, y_centro, y_escala, _ = ajuste
    valor = float(modelo.predict(np.array([[(indice - x_centro) / x_escala]]))[0])
    valor = valor * y_escala + y_centro
    if not math.isfinite(valor):
        raise ValueError("Predicción no finita.")
    # La serie observada admite devoluciones netas negativas; el pronóstico de
    # gasto futuro y sus pruebas siguen la misma política explícita >= 0.
    return max(0.0, valor)


def _pron_metrica(valor):
    if valor is None or not math.isfinite(float(valor)):
        return None
    return float(f"{float(valor):.10g}")


def ejecutar_pronostico_semanal(movimientos, contexto, *, cobertura,
                                grupo_id=None, grupos=()):
    """Pronostica el total de la semana posterior al último domingo cerrado.

    `movimientos`: filas de public.vw_movimiento_analitico_v11, sin recalcular
    gasto_conocido desde monto_transaccion. `cobertura`: intervalos inclusivos
    conocidos, certificados por el backend para este usuario/origen. Su ausencia
    NO prueba gasto cero. No entrena con días de la semana todavía abierta.

    Validación de origen, autenticación y adquisición de instantánea son deberes
    del adaptador. El motor vuelve a filtrar propietario y corte por defensa.
    """
    gid = _pron_grupo_propio(grupo_id, grupos, contexto)
    tipo = "SEMANAL_GRUPO" if gid is not None else "SEMANAL_GLOBAL"
    intervalos = _pron_cobertura(cobertura, contexto)
    # Sunday of current week is not closed until the following local Monday.
    ultimo_domingo = contexto.fecha_local - timedelta(days=contexto.fecha_local.weekday() + 1)
    semanas_desc = []
    domingo = ultimo_domingo
    while len(semanas_desc) < 104:
        lunes = domingo - timedelta(days=6)
        if not any(inicio <= lunes and domingo <= fin for inicio, fin in intervalos):
            break
        semanas_desc.append((lunes, domingo))
        domingo -= timedelta(days=7)
    semanas = list(reversed(semanas_desc))
    n = len(semanas)
    objetivo_inicio = ultimo_domingo + timedelta(days=1)
    objetivo_fin = objetivo_inicio + timedelta(days=6)
    comunes = {
        "tipo_prediccion": tipo, "grupo_id": gid,
        "semanas_completas_utilizadas": n, "semanas_requeridas": 8,
        "periodo_inicio_objetivo": objetivo_inicio.isoformat(),
        "periodo_fin_objetivo": objetivo_fin.isoformat(),
        "objetivo_es_semana_en_curso": objetivo_inicio <= contexto.fecha_local <= objetivo_fin,
        "gasto_estimado": None, "rango_min_ux": None, "rango_max_ux": None,
        "pendiente_semanal": None, "nivel_confiabilidad_ux": None,
    }
    # Validar datos incluso en historial corto: no ocultar entradas corruptas.
    filas = filas_propias(movimientos, contexto, campos=(
        "id_transaccion", "fecha_operacion_transaccion", "fecha_registro_transaccion",
        "gasto_conocido", "grupo_id"))
    normalizadas = []
    ids = set()
    for fila in filas:
        tid = normalizar_uuid(fila["id_transaccion"], "id_transaccion")
        if tid in ids:
            raise DatosInvalidos("Movimiento duplicado: no se puede duplicar gasto conocido.")
        ids.add(tid)
        operacion = fecha_local_valor(fila["fecha_operacion_transaccion"])
        importe = decimal_finito(fila["gasto_conocido"], "gasto_conocido")
        if abs(importe) > Decimal("9999999999.99"):
            raise DatosInvalidos("gasto_conocido excede el importe admitido por la vista SQL.")
        grupo_fila = fila.get("grupo_id")
        if grupo_fila is not None and not pd.isna(grupo_fila):
            grupo_fila = normalizar_uuid(grupo_fila, "grupo_id")
        else:
            grupo_fila = None
        if gid is None or gid == grupo_fila:
            normalizadas.append({
                "id_transaccion": tid, "usuario_id": contexto.usuario_id,
                "fecha_operacion_transaccion": operacion.isoformat(),
                "fecha_registro_transaccion": str(fila["fecha_registro_transaccion"]),
                "grupo_id": grupo_fila, "gasto_conocido": str(importe),
            })
    if n < 8:
        salida = base_respuesta(
            contexto, "HISTORIAL_INSUFICIENTE",
            f"Hay {n} de las 8 semanas consecutivas completas con cobertura conocida "
            "necesarias hasta el último domingo cerrado; no se inventan ceros en semanas sin cobertura.")
        salida.update(comunes)
        salida["ficha_tecnica"] = {
            "tipo_prediccion": tipo, "grupo_id": gid,
            "semanas_completas_utilizadas": n, "semanas_requeridas": 8,
            "cobertura_conocida": bool(n),
            "periodo_inicio_historial": semanas[0][0].isoformat() if semanas else None,
            "periodo_fin_historial": ultimo_domingo.isoformat() if semanas else None,
            "modelo_utilizado": None, "mae_modelo": None, "mae_naive_base": None,
            "rmse_modelo": None, "r2_modelo": None,
        }
        return salida
    inicio = semanas[0][0]
    seleccionadas = [f for f in normalizadas
                     if inicio <= date.fromisoformat(f["fecha_operacion_transaccion"]) <= ultimo_domingo]
    totales = [Decimal("0") for _ in range(n)]
    for fila in seleccionadas:
        indice = (date.fromisoformat(fila["fecha_operacion_transaccion"]) - inicio).days // 7
        totales[indice] += Decimal(fila["gasto_conocido"])
    y = np.array([float(v) for v in totales], dtype=float)
    if not np.isfinite(y).all():
        raise DatosInvalidos("Agregación semanal fuera del rango numérico del modelo.")
    n_train = max(6, int(math.floor(n * 0.8)))
    observados = y[n_train:]
    naive = y[n_train - 1:n - 1].copy()  # Última observación REAL antes de cada objetivo.
    candidatos, predicciones, ajustes = {}, {}, {}
    advertencias = []
    for nombre in ("OLS", "HuberRegressor"):
        try:
            pronosticos = [_pron_predict(_pron_fit(nombre, y[:i]), i)
                           for i in range(n_train, n)]
            ajuste = _pron_fit(nombre, y)
            futuro = _pron_predict(ajuste, n)
            mae = _pron_metrica(mean_absolute_error(observados, pronosticos))
            rmse = _pron_metrica(math.sqrt(mean_squared_error(observados, pronosticos)))
            # En constante o una sola prueba R² no tiene interpretación válida.
            r2 = (_pron_metrica(r2_score(observados, pronosticos))
                  if len(observados) >= 2 and np.var(observados) > 0 else None)
            if mae is None or rmse is None:
                raise ValueError("Métricas no finitas.")
            candidatos[nombre] = {"disponible": True, "mae_modelo": mae,
                                  "rmse_modelo": rmse, "r2_modelo": r2}
            predicciones[nombre] = pronosticos
            ajustes[nombre] = (ajuste, futuro)
        except (ValueError, ArithmeticError, RuntimeError, ConvergenceWarning):
            candidatos[nombre] = {"disponible": False, "mae_modelo": None,
                                  "rmse_modelo": None, "r2_modelo": None,
                                  "motivo": "No produjo ajuste convergente y finito."}
            advertencias.append(f"{nombre} no disponible: convergencia o estabilidad numérica.")
    disponibles = [nombre for nombre in ("OLS", "HuberRegressor")
                   if candidatos[nombre]["disponible"]]
    if not disponibles:
        salida = base_respuesta(contexto, "MODELO_NO_DISPONIBLE",
                               "Los modelos no produjeron un ajuste estable; no se emite un importe ficticio.")
        salida.update(comunes)
        salida["ficha_tecnica"] = {"candidatos": candidatos, "advertencias": advertencias}
        return salida
    # Empate: preferir OLS por simplicidad; no seleccionar por R² de entrenamiento.
    ganador = min(disponibles, key=lambda nombre: candidatos[nombre]["mae_modelo"])
    ajuste, valor = ajustes[ganador]
    metricas = candidatos[ganador]
    mae = metricas["mae_modelo"]
    mae_naive = _pron_metrica(mean_absolute_error(observados, naive))
    pred = Decimal(moneda(Decimal(str(valor))))
    mae_decimal = Decimal(str(mae))
    rango_min = moneda(max(Decimal("0"), pred - mae_decimal))
    rango_max = moneda(pred + mae_decimal)
    if max(pred, Decimal(rango_max)) > Decimal("9999999999.99"):
        raise DatosInvalidos("El pronóstico excede la capacidad NUMERIC(12,2) de PREDICCION.")
    media_evaluada = float(np.mean(observados))
    razon = mae / media_evaluada if media_evaluada > 0 else None
    if razon is None or not math.isfinite(razon):
        confianza = "BAJA"
    elif mae <= mae_naive and razon < 0.15:
        confianza = "ALTA"
    elif razon < 0.30:
        confianza = "MEDIA"
    else:
        confianza = "BAJA"
    periodo_texto = f"{objetivo_inicio.isoformat()} al {objetivo_fin.isoformat()}"
    explicacion = (
        f"Estimamos un gasto neto total de ${moneda(pred)} MXN para la semana del {periodo_texto}. "
        f"La banda descriptiva es de ${rango_min} a ${rango_max} MXN (estimación ± error MAE observado); "
        "no es un intervalo de confianza ni garantiza el gasto futuro. "
        f"Indicador heurístico de confiabilidad: {confianza}. "
        + ("Este total incluye toda la semana en curso, no solo sus días restantes. "
           if comunes["objetivo_es_semana_en_curso"] else "")
        + ("En esta evaluación el modelo no superó la referencia de la última semana."
           if mae > mae_naive else "La evaluación cronológica no garantiza resultados futuros.")
    )
    huella = hash_datos(contexto, tipo, seleccionadas, parametros={
        "grupo_id": gid, "inicio": inicio.isoformat(), "fin": ultimo_domingo.isoformat(),
        "semanas": n, "cobertura_conocida": True,
        "validacion": "walk_forward_expanding_80_20", "baseline": "ultima_semana_real",
        "politica_ux": "PRD09_media_evaluada_0.15_0.30",
        "huber": {"epsilon": 1.35, "alpha": 0.0, "max_iter": 2000, "tol": 1e-8},
    })
    salida = base_respuesta(contexto, "OK", explicacion, huella)
    salida.update(comunes)
    salida.update({"gasto_estimado": moneda(pred), "rango_min_ux": rango_min,
                   "rango_max_ux": rango_max, "pendiente_semanal": _pron_metrica(ajuste[-1]),
                   "nivel_confiabilidad_ux": confianza})
    ficha = {
        "tipo_prediccion": tipo, "grupo_id": gid, "periodo_id": None,
        "periodo_inicio_historial": inicio.isoformat(),
        "periodo_fin_historial": ultimo_domingo.isoformat(),
        "periodo_inicio_objetivo": objetivo_inicio.isoformat(),
        "periodo_fin_objetivo": objetivo_fin.isoformat(),
        "semanas_completas_utilizadas": n, "cobertura_conocida": True,
        "cobertura": {"fecha_inicio": inicio.isoformat(), "fecha_fin": ultimo_domingo.isoformat(),
                      "fuente": "intervalos_inclusivos_certificados_por_backend"},
        "modelo_utilizado": ganador, "mae_modelo": mae, "mae_naive_base": mae_naive,
        "rmse_modelo": metricas["rmse_modelo"], "r2_modelo": metricas["r2_modelo"],
        "pendiente_tendencia_semanal": _pron_metrica(ajuste[-1]),
        "pendiente": _pron_metrica(ajuste[-1]), "huella_datos": huella,
        "validacion": "80/20 cronológica; reajuste expansivo antes de cada semana de prueba",
        "limitacion_evaluacion": "El tramo cronológico compara y selecciona candidatos; no es una prueba externa independiente posterior a la selección.",
        "limite_semanas_historial": 104,
        "semanas_entrenamiento_inicial": n_train, "semanas_evaluacion": n - n_train,
        "baseline": "Última semana real, actualizada antes de cada objetivo",
        "politica_prediccion": "Pronósticos OLS/Huber truncados a >=0; observaciones y baseline firmados",
        "politica_confiabilidad": "PRD09: media evaluada positiva; ALTA MAE<=Naive y razón<0.15; MEDIA razón<0.30; BAJA resto",
        "media_semanal_evaluada": _pron_metrica(media_evaluada),
        "razon_mae_media_evaluada": _pron_metrica(razon),
        "banda": "Descriptiva ±MAE; no intervalo probabilístico calibrado",
        "candidatos": candidatos, "advertencias": advertencias,
        "serie_semanal": [{"fecha_inicio": semana[0].isoformat(),
                           "fecha_fin": semana[1].isoformat(), "gasto_conocido": moneda(total)}
                          for semana, total in zip(semanas, totales)],
        "evaluacion": [{"fecha_inicio": semanas[i][0].isoformat(),
                        "observado": moneda(totales[i]), "naive": moneda(Decimal(str(naive[i - n_train]))),
                        "prediccion": moneda(Decimal(str(predicciones[ganador][i - n_train])))}
                       for i in range(n_train, n)],
    }
    salida["ficha_tecnica"] = ficha
    return salida


# ---------------------------------------------------------------------------
# Análisis del periodo y proyecciones deterministas. Importes de las vistas SQL.
# ---------------------------------------------------------------------------

_PER_CLUSTER_VERSION = "fintrack-v1.1-kmeans-logmonto-1.0.0"
_PER_FUZZY_VERSION = "fintrack-v1.1-mamdani-2f-1.0.0"
_PER_FUZZY_TREND_VERSION = "fintrack-v1.1-mamdani-3f-1.0.0"
_PER_PROJECTION_VERSION = "fintrack-v1.1-proyeccion-determinista-1.0.0"


def _per_instante(valor, nombre):
    if isinstance(valor, datetime):
        instante = valor
    elif isinstance(valor, str):
        try:
            instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DatosInvalidos(f"{nombre}: fecha/hora inválida") from exc
    else:
        raise DatosInvalidos(f"{nombre}: se requiere fecha/hora con zona")
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise DatosInvalidos(f"{nombre}: se requiere zona horaria")
    return instante


def _per_fila_propia(fila, contexto, identificador):
    if not isinstance(fila, dict):
        raise DatosInvalidos("Se requiere un objeto con los campos de la vista SQL")
    if normalizar_uuid(fila.get("usuario_id")) != normalizar_uuid(contexto.usuario_id):
        raise DatosInvalidos("El objeto no pertenece al usuario del contexto")
    normalizar_uuid(fila.get(identificador))
    return dict(fila)


def _per_numero(fila, campo, *, no_negativo=False):
    if campo not in fila or fila[campo] is None:
        raise DatosInvalidos(f"Falta {campo}; consultar la vista SQL indicada")
    valor = decimal_finito(fila[campo], campo)
    try:
        representable = math.isfinite(float(valor))
    except (ValueError, OverflowError):
        representable = False
    if not representable:
        raise DatosInvalidos(f"{campo} fuera del rango numérico evaluable")
    if no_negativo and valor < 0:
        raise DatosInvalidos(f"{campo} no puede ser negativo")
    return valor


def _per_ventana(periodo, contexto):
    inicio = fecha_local_valor(periodo["fecha_inicio_periodo"])
    fin = fecha_local_valor(periodo["fecha_fin_periodo"])
    if inicio > fin:
        raise DatosInvalidos("Las fechas del periodo están invertidas")
    corte = contexto.fecha_local
    dias_totales = (fin - inicio).days + 1
    hasta = min(corte, fin)
    if periodo.get("estado_periodo") != "ACTIVO" and periodo.get("fecha_cierre_periodo") is not None:
        cierre = _per_instante(periodo["fecha_cierre_periodo"], "fecha_cierre_periodo")
        if cierre > contexto.fecha_corte_datos:
            raise DatosInvalidos("El cierre del periodo es posterior al corte solicitado")
        hasta = min(hasta, fecha_local_valor(cierre))
    dias_observados = max(0, (hasta - inicio).days + 1)
    return inicio, fin, corte, dias_totales, dias_observados


def ejecutar_clustering_hormiga(transacciones, contexto, *, periodo=None):
    """K-Means k=3 sobre log1p de GASTO del periodo efectivo SQL.

    ``periodo`` es la fila propia de public.periodo seleccionada por el adapter.
    Si no existe periodo ACTIVO y no se solicitó uno explícito, pasar None.
    Los datos deben venir de vw_transaccion_periodo_v11, nunca inferir periodo
    por el orden del DataFrame. Un importe pequeño no implica gasto innecesario.
    """
    if periodo is None:
        respuesta = base_respuesta(contexto, "SIN_PERIODO_ACTIVO", "No hay un periodo activo seleccionado para analizar.")
        respuesta.update(tipo_prediccion="KMEANS_HORMIGA", grupo_id=None, periodo_id=None, clusters=[], total_gastos_analizados=0,
                         version_modelo=_PER_CLUSTER_VERSION, ficha_tecnica=None)
        return respuesta
    periodo = _per_fila_propia(periodo, contexto, "id_periodo")
    pid = normalizar_uuid(periodo["id_periodo"])
    inicio, fin, corte, _, _ = _per_ventana(periodo, contexto)
    filas = filas_propias(transacciones, contexto, campos=("id_transaccion", "periodo_id", "tipo_transaccion", "monto_transaccion", "fecha_operacion_transaccion", "fecha_registro_transaccion"))
    gastos, vistos = [], set()
    for fila in filas:
        if fila.get("periodo_id") is None or normalizar_uuid(fila["periodo_id"]) != pid:
            continue
        if fila["tipo_transaccion"] != "GASTO":
            continue
        fecha = fecha_local_valor(fila["fecha_operacion_transaccion"])
        registro = _per_instante(fila["fecha_registro_transaccion"], "fecha_registro_transaccion")
        if registro > contexto.fecha_corte_datos or fecha > corte:
            continue
        if not inicio <= fecha <= fin:
            raise DatosInvalidos("Un GASTO del periodo efectivo tiene fecha fuera de sus límites")
        tid = normalizar_uuid(fila["id_transaccion"])
        if tid in vistos:
            raise DatosInvalidos("Transacción duplicada; no unir vistas que multipliquen filas")
        vistos.add(tid)
        monto = decimal_finito(fila["monto_transaccion"], "monto_transaccion", positivo=True)
        gastos.append({"id_transaccion": tid, "fecha": fecha.isoformat(), "monto": monto})
    gastos.sort(key=lambda x: x["id_transaccion"])
    parametros = {"periodo_id": pid, "version": _PER_CLUSTER_VERSION, "k": 3,
                  "transformacion": "log1p(monto_transaccion)", "random_state": 42, "n_init": 10}
    huella = hash_datos(contexto, "KMEANS_HORMIGA", gastos, parametros=parametros)
    total = len(gastos)
    distintos = len({g["monto"] for g in gastos})
    if total < 6 or distintos < 3:
        respuesta = base_respuesta(contexto, "DATOS_INSUFICIENTES", f"Hay {total} gastos y {distintos} importes distintos: se requieren al menos 6 gastos y 3 importes distintos para segmentar.", huella=huella)
        respuesta.update(tipo_prediccion="KMEANS_HORMIGA", grupo_id=None, periodo_id=pid, total_gastos_analizados=total, clusters=[],
                         version_modelo=_PER_CLUSTER_VERSION,
                         ficha_tecnica={**parametros, "minimo_gastos": 6, "minimo_importes_distintos": 3})
        return respuesta
    montos = np.array([float(g["monto"]) for g in gastos], dtype=float)
    if not np.isfinite(montos).all() or np.any(montos <= 0):
        raise DatosInvalidos("Importes fuera del rango numérico para clustering")
    x = np.log1p(montos).reshape(-1, 1)
    modelo = KMeans(n_clusters=3, random_state=42, n_init=10)
    etiquetas = modelo.fit_predict(x)
    centros = modelo.cluster_centers_[:, 0]
    orden = sorted(range(3), key=lambda k: (float(centros[k]), k))
    suma_total = sum((g["monto"] for g in gastos), Decimal("0"))
    nombres = ("Gastos pequeños", "Gastos intermedios", "Gastos mayores")
    clusters = []
    for nuevo, viejo in enumerate(orden):
        miembros = [g for i, g in enumerate(gastos) if int(etiquetas[i]) == viejo]
        if not miembros:
            raise DatosInvalidos("El modelo no produjo tres segmentos no vacíos")
        suma = sum((g["monto"] for g in miembros), Decimal("0"))
        cantidad = len(miembros)
        clusters.append({"cluster_id": nuevo, "etiqueta": nombres[nuevo],
                         "conteo": cantidad, "suma": moneda(suma), "media": moneda(suma / cantidad),
                         "monto_minimo": moneda(min(g["monto"] for g in miembros)),
                         "monto_maximo": moneda(max(g["monto"] for g in miembros)),
                         "porcentaje_operaciones": round(100 * cantidad / total, 2),
                         "porcentaje_dinero": round(float(100 * suma / suma_total), 2),
                         "centroide_tecnico": {"log1p_monto": round(float(centros[viejo]), 8),
                                               "importe_equivalente": moneda(Decimal(str(math.expm1(float(centros[viejo])))))}})
    pequenos = clusters[0]
    texto = (f"En el periodo, {pequenos['conteo']} gastos pertenecen al segmento de importes pequeños: "
             f"suman ${pequenos['suma']} MXN ({pequenos['porcentaje_dinero']:.2f}% del dinero analizado) "
             f"y representan {pequenos['porcentaje_operaciones']:.2f}% de las operaciones. "
             "Son candidatos a revisión; su tamaño no demuestra que sean innecesarios o evitables.")
    respuesta = base_respuesta(contexto, "OK", texto, huella=huella)
    respuesta.update(tipo_prediccion="KMEANS_HORMIGA", grupo_id=None, periodo_id=pid, version_modelo=_PER_CLUSTER_VERSION,
                     total_gastos_analizados=total, suma_gastos_analizados=moneda(suma_total), clusters=clusters,
                     periodo_inicio_historial=inicio.isoformat(), periodo_fin_historial=min(fin, corte).isoformat(),
                     ficha_tecnica={**parametros, "modelo_utilizado": "KMeans", "variables": ["log1p(monto_transaccion)"],
                                    "inercia": round(float(modelo.inertia_), 8),
                                    "advertencia": "Segmentación exploratoria no supervisada; no clasifica necesidades ni determina ahorro garantizado."})
    return respuesta


def proyectar_periodo(resumen_periodo, contexto):
    """Extrapolación determinista del APLICADO; no es regresión ni se persiste."""
    periodo = _per_fila_propia(resumen_periodo, contexto, "id_periodo")
    inicio, fin, corte, duracion, observados = _per_ventana(periodo, contexto)
    respuesta = {"metodo": "PROYECCION_DETERMINISTA", "version_modelo": _PER_PROJECTION_VERSION,
                 "periodo_id": normalizar_uuid(periodo["id_periodo"]), "estado": None,
                 "aplicado_estimado_cierre": None, "ritmo_diario_aplicado": None,
                 "fecha_corte_datos": contexto.fecha_corte_datos.isoformat(), "supuestos": [],
                 "ventana_inicio": inicio.isoformat(), "ventana_fin": (inicio + timedelta(days=observados - 1)).isoformat() if observados else None,
                 "dias_observados": observados, "dias_periodo": duracion}
    if periodo.get("estado_periodo") != "ACTIVO":
        respuesta.update(estado="PERIODO_CERRADO", motivo="El periodo no está activo; consultar su resultado histórico, no una proyección.")
        return respuesta
    if observados <= 0:
        respuesta.update(estado="SIN_VENTANA_OBSERVADA", motivo="El periodo aún no tiene días observados al corte.")
        return respuesta
    if corte > fin:
        respuesta.update(estado="PERIODO_VENCIDO", motivo="La fecha de cierre ya pasó; no se proyecta una fecha pasada.")
        return respuesta
    aplicado = _per_numero(periodo, "aplicado_total_periodo")
    if aplicado < 0:
        respuesta.update(estado="RITMO_NO_EVALUABLE", motivo="El aplicado neto es negativo por devoluciones; no se extrapola como consumo futuro.")
        return respuesta
    base = _per_numero(periodo, "monto_presupuesto_periodo", no_negativo=True)
    if base <= 0:
        respuesta.update(estado="SIN_BASE_EVALUABLE", motivo="No hay presupuesto positivo para interpretar el consumo proyectado.")
        return respuesta
    ritmo = aplicado / Decimal(observados)
    estimado = ritmo * Decimal(duracion)
    respuesta.update(estado="OK", aplicado_estimado_cierre=moneda(estimado), ritmo_diario_aplicado=moneda(ritmo),
                     diferencia_vs_presupuesto=moneda(estimado - base),
                     supuestos=["Mantener el ritmo medio de Aplicado del dinero registrado desde el inicio del periodo.",
                                "Días calendario inclusivos: el día del corte puede estar incompleto.",
                                "No anticipa ingresos, devoluciones ni pagos programados; no es una predicción ML."])
    return respuesta


def proyectar_meta(meta, contexto):
    """Fecha orientativa por neto APORTE-RETIRO desde creación, no mueve dinero."""
    meta = _per_fila_propia(meta, contexto, "id_meta")
    respuesta = {"metodo": "PROYECCION_DETERMINISTA", "version_modelo": _PER_PROJECTION_VERSION,
                 "meta_id": normalizar_uuid(meta["id_meta"]), "estado": None,
                 "fecha_estimada_cumplimiento": None, "ritmo_neto_diario": None,
                 "fecha_corte_datos": contexto.fecha_corte_datos.isoformat(), "supuestos": []}
    if meta.get("estado_meta") != "ACTIVA":
        respuesta.update(estado="META_CERRADA", motivo="La meta está cerrada; no se calcula una nueva fecha de cumplimiento.")
        return respuesta
    creacion = _per_instante(meta.get("fecha_creacion_meta"), "fecha_creacion_meta")
    dias = Decimal(str((contexto.fecha_corte_datos - creacion).total_seconds())) / Decimal("86400")
    respuesta.update(ventana_inicio=creacion.isoformat(), ventana_fin=contexto.fecha_corte_datos.isoformat(), dias_observados=round(float(dias), 4))
    if dias < 1:
        respuesta.update(estado="HISTORIAL_INSUFICIENTE", motivo="Se requiere al menos un día completo desde la creación para extrapolar un ritmo neto.")
        return respuesta
    actual = _per_numero(meta, "monto_actual_meta", no_negativo=True)
    objetivo = _per_numero(meta, "monto_objetivo_meta", no_negativo=True)
    if objetivo <= 0 or actual > objetivo:
        raise DatosInvalidos("Acumulado u objetivo de meta incompatible con el contrato SQL")
    if actual == objetivo:
        respuesta.update(estado="OBJETIVO_CUBIERTO", fecha_estimada_cumplimiento=contexto.fecha_local.isoformat(),
                         motivo="El neto actual ya cubre el objetivo; esta es la fecha del corte, no una fecha histórica inferida.")
        return respuesta
    if actual <= 0:
        respuesta.update(estado="RITMO_NO_POSITIVO", motivo="No hay ritmo neto positivo de aportes menos retiros.")
        return respuesta
    ritmo = actual / dias
    dias_restantes = math.ceil((objetivo - actual) / ritmo)
    try:
        fecha_estimada = contexto.fecha_local + timedelta(days=dias_restantes)
    except OverflowError:
        respuesta.update(estado="FUERA_DE_RANGO", motivo="El ritmo es demasiado bajo para una fecha representable.")
        return respuesta
    limite = fecha_local_valor(meta["fecha_limite_meta"]) if meta.get("fecha_limite_meta") is not None else None
    respuesta.update(estado="OK", fecha_estimada_cumplimiento=fecha_estimada.isoformat(), ritmo_neto_diario=moneda(ritmo),
                     rebasa_fecha_limite=(fecha_estimada > limite) if limite else None,
                     supuestos=["Mantener el ritmo neto APORTE menos RETIRO desde la creación de la meta, sumando sus cuentas aportantes.",
                                "El acumulado debe proceder de vw_meta_resumen_v11 y corresponder al mismo corte.",
                                "No crea transferencias ni garantiza aportaciones futuras; no es una predicción ML."])
    return respuesta


def _per_hombro_alto(valor, bajo, alto):
    """Pertenencia saturante; no vuelve a cero fuera del universo nominal."""
    if valor <= bajo:
        return 0.0
    if valor >= alto:
        return 1.0
    return (valor - bajo) / (alto - bajo)


def _per_mamdani(riesgos):
    """Dos reglas exhaustivas Mamdani, implicación min, agregación max.

    BAJO = 1-ALTO en cada antecedente. R1=AND de BAJOS; R2=OR de ALTOS.
    Por dualidad, R1=1-R2. Elevar cualquier riesgo nunca mejora el centroide.
    La salida se integra sobre un universo 0..100 con paso 0.1.
    """
    alto = max(riesgos)
    favorable = min(1.0 - riesgo for riesgo in riesgos)
    universo = np.linspace(0.0, 100.0, 1001)
    salida_riesgo = np.clip((50.0 - universo) / 50.0, 0.0, 1.0)
    salida_favorable = np.clip((universo - 50.0) / 50.0, 0.0, 1.0)
    agregado = np.maximum(np.minimum(alto, salida_riesgo), np.minimum(favorable, salida_favorable))
    area = float(np.sum(agregado))
    if area <= 0 or not math.isfinite(area):
        raise DatosInvalidos("La base de reglas difusas no produjo una salida evaluable")
    centroide = float(np.dot(universo, agregado) / area)
    return centroide, {"R1_TODOS_BAJOS_SALUD_FAVORABLE": round(favorable, 8),
                       "R2_CUALQUIERA_ALTO_SALUD_EN_RIESGO": round(alto, 8)}


def evaluar_salud_difusa_periodo(resumen_periodo, detalles_grupo, contexto, *, pronostico=None):
    """Salud orientativa Mamdani sobre métricas ya calculadas por PostgreSQL.

    resumen_periodo: fila de vw_periodo_resumen_v11 con intereses_periodo
    agregado por el adapter = SUM(monto_transaccion-monto_reduccion_deuda)
    exclusivamente PAGO_DEUDA en vw_transaccion_periodo_v11, mismo corte.
    El campo adicional NO existe como columna de la vista original.
    detalles_grupo: cuatro filas de vw_detalle_periodo_grupo_v11 propias.
    Sin pronóstico global válido se usa una variante parcial explícita con
    velocidad e intereses; no se sustituye la tendencia faltante por cero.
    """
    periodo = _per_fila_propia(resumen_periodo, contexto, "id_periodo")
    pid = normalizar_uuid(periodo["id_periodo"])
    inicio, fin, corte, duracion, observados = _per_ventana(periodo, contexto)
    proyeccion = proyectar_periodo(periodo, contexto)
    respuesta = base_respuesta(contexto, "SIN_BASE_EVALUABLE", "No hay base o ventana suficiente para evaluar la salud orientativa del periodo.")
    respuesta.update(tipo_prediccion="SALUD_DIFUSA", grupo_id=None, periodo_id=pid, score_salud_difuso=None, etiqueta_salud=None,
                     factores_disponibles={}, proyeccion_periodo=proyeccion,
                     version_modelo=_PER_FUZZY_VERSION, ficha_tecnica=None)
    if observados <= 0:
        return respuesta
    presupuesto = _per_numero(periodo, "monto_presupuesto_periodo", no_negativo=True)
    if presupuesto <= 0:
        return respuesta
    if "intereses_periodo" not in periodo or periodo["intereses_periodo"] is None:
        respuesta["explicacion_ux"] = "Falta el agregado de intereses del periodo requerido por el adapter; no se inventa presión de deuda cero."
        return respuesta
    intereses = _per_numero(periodo, "intereses_periodo", no_negativo=True)
    pagos = _per_numero(periodo, "pagos_deuda_periodo", no_negativo=True)
    if intereses > pagos:
        raise DatosInvalidos("Los intereses del periodo no pueden superar los pagos de deuda")
    aplicado = _per_numero(periodo, "aplicado_total_periodo")
    detalles = filas_propias(detalles_grupo, contexto, campos=("periodo_id", "grupo_id", "codigo_grupo", "monto_presupuesto_grupo", "aplicado_dinero_grupo"))
    detalles = [d for d in detalles if normalizar_uuid(d["periodo_id"]) == pid]
    if len(detalles) != 4 or {d["codigo_grupo"] for d in detalles} != {"G001", "G002", "G003", "G004"}:
        raise DatosInvalidos("Se requieren los cuatro grupos distintos del periodo propio")
    suma_plan = sum((_per_numero(d, "monto_presupuesto_grupo", no_negativo=True) for d in detalles), Decimal("0"))
    suma_aplicado = sum((_per_numero(d, "aplicado_dinero_grupo") for d in detalles), Decimal("0"))
    if abs(suma_plan - presupuesto) > Decimal("0.005") or abs(suma_aplicado - aplicado) > Decimal("0.005"):
        raise DatosInvalidos("Resumen y detalles no corresponden a la misma instantánea SQL")
    fraccion_tiempo = Decimal(observados) / Decimal(duracion)
    velocidad = max(Decimal("0"), aplicado) / presupuesto / fraccion_tiempo
    grupos_sin_base = [d["codigo_grupo"] for d in detalles if _per_numero(d, "monto_presupuesto_grupo") == 0 and _per_numero(d, "aplicado_dinero_grupo") > 0]
    riesgo_velocidad = max(_per_hombro_alto(float(velocidad), 0.8, 1.5), 1.0 if grupos_sin_base else 0.0)
    presion = intereses / pagos if pagos > 0 else Decimal("0")
    riesgo_presion = _per_hombro_alto(float(presion), 0.1, 0.5)
    factores = {
        "velocidad_aplicado": {"valor": round(float(velocidad), 6),
                               "definicion": "max(0, aplicado_total_periodo) / monto_presupuesto_periodo / fracción_días_transcurridos",
                               "fraccion_dias_transcurridos": round(float(fraccion_tiempo), 6),
                               "dias_observados": observados, "dias_periodo": duracion,
                               "grupos_con_aplicado_sin_presupuesto": grupos_sin_base,
                               "pertenencia_riesgo_alto": round(riesgo_velocidad, 8)},
        "presion_intereses": {"valor": round(float(presion), 6),
                              "definicion": "intereses del PAGO_DEUDA / pagos_deuda_periodo; 0 solo cuando ambos son 0",
                              "intereses_periodo": moneda(intereses), "pagos_deuda_periodo": moneda(pagos),
                              "pertenencia_riesgo_alto": round(riesgo_presion, 8)}}
    riesgos = [riesgo_velocidad, riesgo_presion]
    variante = "PARCIAL_2_FACTORES"
    version = _PER_FUZZY_VERSION
    motivo_tendencia = "Sin pronóstico global compatible: no se usa un valor de tendencia ficticio."
    if isinstance(pronostico, dict) and pronostico.get("estado") == "OK":
        mismo_origen = pronostico.get("origen_datos") == contexto.origen_datos
        grupo_global = pronostico.get("grupo_id") is None
        corte_pronostico = pronostico.get("fecha_corte_datos")
        mismo_corte = corte_pronostico is not None and _per_instante(corte_pronostico, "fecha_corte_datos del pronóstico") == contexto.fecha_corte_datos
        mismo_contexto = pronostico.get("contexto_analitico") == sello_contexto(contexto)
        if mismo_origen and grupo_global and mismo_corte and mismo_contexto and pronostico.get("version_modelo") and pronostico.get("pendiente_semanal") is not None:
            pendiente = decimal_finito(pronostico["pendiente_semanal"], "pendiente_semanal")
            referencia_semanal = presupuesto * Decimal(7) / Decimal(duracion)
            tendencia = pendiente / referencia_semanal
            riesgo_tendencia = _per_hombro_alto(float(tendencia), 0.0, 0.2)
            factores["tendencia_gasto"] = {"valor": round(float(tendencia), 6),
                                           "pendiente_semanal": float(pendiente),
                                           "version_modelo_fuente": pronostico["version_modelo"],
                                           "definicion": "pendiente del gasto global / (presupuesto del periodo × 7 / días_periodo)",
                                           "pertenencia_riesgo_alto": round(riesgo_tendencia, 8)}
            riesgos.append(riesgo_tendencia)
            variante = "COMPLETA_3_FACTORES"
            version = _PER_FUZZY_TREND_VERSION
            motivo_tendencia = None
    score, activaciones = _per_mamdani(riesgos)
    if score >= 70:
        etiqueta = "FAVORABLE"
    elif score >= 40:
        etiqueta = "PRECAUCION"
    else:
        etiqueta = "EN_RIESGO"
    parametros = {"version": version, "variante": variante, "universo_salida": [0, 100], "paso": 0.1,
                  "inferencia": "MAMDANI", "conjuncion": "min", "disyuncion": "max",
                  "implicacion": "min", "agregacion": "max", "defuzzificacion": "centroide",
                  "hombro_velocidad": [0.8, 1.5], "hombro_presion_intereses": [0.1, 0.5],
                  "hombro_tendencia": [0.0, 0.2] if len(riesgos) == 3 else None,
                  "reglas": ["R1: todos los factores BAJOS -> SALUD_FAVORABLE", "R2: cualquiera de los factores ALTO -> SALUD_EN_RIESGO"],
                  "salidas": {"SALUD_EN_RIESGO": "hombro izquierdo 0..50", "SALUD_FAVORABLE": "hombro derecho 50..100"}}
    huella = hash_datos(contexto, "SALUD_DIFUSA", {"periodo_id": pid, "inicio": inicio.isoformat(), "fin": fin.isoformat(),
                        "presupuesto": presupuesto, "aplicado": aplicado, "intereses": intereses, "pagos": pagos,
                        "factores": factores}, parametros=parametros)
    texto = (f"Salud orientativa del periodo: {score:.1f}/100 ({etiqueta}). "
             f"El aplicado equivale a {float(velocidad):.2f} veces el ritmo uniforme previsto y "
             f"los intereses representan {float(presion * 100):.1f}% de los pagos de deuda. "
             "El indicador no es un diagnóstico ni bloquea movimientos.")
    if variante == "PARCIAL_2_FACTORES":
        texto += " Evaluación parcial de dos factores; la tendencia semanal aún no participa."
    respuesta = base_respuesta(contexto, "OK", texto, huella=huella)
    respuesta.update(tipo_prediccion="SALUD_DIFUSA", grupo_id=None, periodo_id=pid, version_modelo=version, score_salud_difuso=round(score, 1),
                     etiqueta_salud=etiqueta, factores_disponibles=factores, proyeccion_periodo=proyeccion,
                     periodo_inicio_historial=inicio.isoformat(), periodo_fin_historial=(inicio + timedelta(days=observados - 1)).isoformat(),
                     ficha_tecnica={"modelo_utilizado": "Mamdani", "variante": variante,
                                    "activaciones_reglas": activaciones, "parametros": parametros,
                                    "tendencia_no_disponible_motivo": motivo_tendencia,
                                    "advertencias": ["Umbrales heurísticos versionados: requieren validación con usuarios, no una precisión garantizada.",
                                                     "Asume ritmo uniforme; pagos concentrados al inicio pueden elevar el riesgo orientativo.",
                                                     "Los intereses vienen de un agregado adicional del adapter, no de una columna inexistente de la vista.",
                                                     "Las salidas Mamdani están en 0..100; su centroide no tiene por qué alcanzar los extremos."]})
    return respuesta


# ---------------------------------------------------------------------------
# Autoclasificación privada, conservadora y sin escritura de movimientos.
# No usa un lexicón comercial como si fuera un modelo preentrenado/calibrado.
# ---------------------------------------------------------------------------

CLASIFICADOR_VERSION = "tfidf_nb_privado_v1.1.0"
CLASIFICADOR_PARAMETROS = {
    "min_documentos_nb": 6,
    "min_clases_nb": 2,
    "min_repeticiones_exactas": 2,
    "max_documentos": 2000,
    "ngram_range": [1, 2],
    "alpha_nb": 1.0,
    "min_similitud_coseno": 0.55,
    "min_brecha_similitud_clases": 0.10,
    "min_probabilidad_no_calibrada": 0.60,
    "min_margen_probabilidades": 0.15,
}
_CLAS_STOPWORDS = [
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "el",
    "ella", "ellas", "ellos", "en", "entre", "era", "es", "esa", "ese", "eso",
    "esta", "este", "esto", "fue", "la", "las", "lo", "los", "mi", "mis",
    "o", "para", "por", "que", "se", "sin", "sobre", "su", "sus", "un", "una",
    "unas", "unos", "y", "yo",
]


def _clas_ausente(valor):
    if valor is None:
        return True
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        return False


def _clas_texto(valor):
    if _clas_ausente(valor):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor)).casefold()
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _clas_filas(datos):
    if datos is None:
        return []
    if isinstance(datos, pd.DataFrame):
        return datos.to_dict(orient="records")
    if isinstance(datos, (list, tuple)) and all(isinstance(f, dict) for f in datos):
        return [dict(f) for f in datos]
    raise DatosInvalidos("El catálogo de subcategorías debe ser una lista de objetos o DataFrame.")


def _clas_es_activo(valor):
    # Un string "false" nunca debe ser interpretado como True por su contenido.
    return isinstance(valor, (bool, np.bool_)) and bool(valor)


def _clas_uuid_opcional(valor):
    return None if _clas_ausente(valor) else normalizar_uuid(valor)


def _clas_agregar_sin_duplicados(destino, clave, registro, nombre):
    if clave in destino and destino[clave] != registro:
        raise DatosInvalidos(f"El catálogo contiene un UUID duplicado y contradictorio de {nombre}.")
    destino[clave] = registro


def sugerir_clasificacion_texto(
    detalle, historial, categorias, subcategorias, grupos, contexto
):
    """Sugiere, nunca aplica, una clasificación a partir del historial GASTO propio.

    La evidencia de memoria exige dos ejemplos exactos y no contradictorios. El
    camino ML usa TF-IDF + MultinomialNB y filtros de relevancia, no una precisión
    inventada. ``confianza`` permanece null: predict_proba no está calibrado.
    Subcategoría es opcional y toda salida se une al catálogo activo ACTUAL del
    mismo usuario. No crea filas PREDICCION ni modifica las etiquetas históricas.
    """
    if not isinstance(detalle, str):
        raise DatosInvalidos("detalle debe ser texto.")
    if not 3 <= len(detalle.strip()) <= 500:
        raise DatosInvalidos("detalle debe contener entre 3 y 500 caracteres.")
    consulta = _clas_texto(detalle)
    if len(consulta) < 3:
        raise DatosInvalidos("detalle no contiene al menos tres caracteres de texto útiles.")

    grupos_propios = filas_propias(
        grupos, contexto,
        campos=("id_grupo", "codigo_grupo", "nombre_grupo", "es_activo_grupo"),
    )
    grupos_por_id = {}
    for fila in grupos_propios:
        if not _clas_es_activo(fila["es_activo_grupo"]):
            continue
        gid = normalizar_uuid(fila["id_grupo"])
        codigo = str(fila["codigo_grupo"])
        if codigo not in {"G001", "G002", "G003", "G004"}:
            raise DatosInvalidos("El clasificador recibió un grupo ajeno a los cuatro maestros V1.1.")
        _clas_agregar_sin_duplicados(
            grupos_por_id, gid,
            {"grupo_id": gid, "codigo_grupo": codigo, "nombre_grupo": str(fila["nombre_grupo"])},
            "grupo",
        )

    categorias_propias = filas_propias(
        categorias, contexto,
        campos=("id_categoria", "grupo_id", "nombre_categoria", "es_activa_categoria"),
    )
    categorias_por_id = {}
    for fila in categorias_propias:
        if not _clas_es_activo(fila["es_activa_categoria"]):
            continue
        cid, gid = normalizar_uuid(fila["id_categoria"]), normalizar_uuid(fila["grupo_id"])
        if gid not in grupos_por_id:
            continue
        _clas_agregar_sin_duplicados(
            categorias_por_id, cid,
            {"categoria_id": cid, "grupo_id": gid, "nombre_categoria": str(fila["nombre_categoria"])},
            "categoría",
        )

    subcategorias_por_id = {}
    for fila in _clas_filas(subcategorias):
        # SUBCATEGORIA no lleva usuario_id en Neon: su propietario se obtiene
        # exclusivamente por JOIN de categoria_id con categorías propias.
        if _clas_ausente(fila.get("categoria_id")):
            continue
        cid = normalizar_uuid(fila["categoria_id"])
        if cid not in categorias_por_id:
            continue
        if "usuario_id" in fila and not _clas_ausente(fila["usuario_id"]):
            if normalizar_uuid(fila["usuario_id"]) != contexto.usuario_id:
                continue
        for campo in ("id_subcategoria", "nombre_subcategoria", "es_activa_subcategoria"):
            if campo not in fila:
                raise DatosInvalidos(f"Falta {campo} en una subcategoría propia.")
        if not _clas_es_activo(fila["es_activa_subcategoria"]):
            continue
        sid = normalizar_uuid(fila["id_subcategoria"])
        _clas_agregar_sin_duplicados(
            subcategorias_por_id, sid,
            {"subcategoria_id": sid, "categoria_id": cid, "nombre_subcategoria": str(fila["nombre_subcategoria"])},
            "subcategoría",
        )

    movimientos = filas_propias(
        historial, contexto,
        campos=("id_transaccion", "tipo_transaccion", "categoria_id",
                "comentario_transaccion", "fecha_registro_transaccion"),
    )
    documentos_por_id = {}
    excluidas = Counter()
    for fila in movimientos:
        if str(fila["tipo_transaccion"]) != "GASTO":
            excluidas["tipo_no_gasto"] += 1
            continue
        cid = _clas_uuid_opcional(fila["categoria_id"])
        if cid not in categorias_por_id:
            excluidas["categoria_no_elegible"] += 1
            continue
        sid = _clas_uuid_opcional(fila.get("subcategoria_id"))
        if sid is not None:
            sub = subcategorias_por_id.get(sid)
            if sub is None or sub["categoria_id"] != cid:
                excluidas["subcategoria_no_elegible"] += 1
                continue
        comentario = fila["comentario_transaccion"]
        if _clas_ausente(comentario) or not isinstance(comentario, str):
            excluidas["sin_texto_util"] += 1
            continue
        texto = _clas_texto(comentario)
        if len(texto) < 3 or len(comentario) > 500:
            excluidas["sin_texto_util"] += 1
            continue
        tid = normalizar_uuid(fila["id_transaccion"])
        documento = {
            "id_transaccion": tid,
            "texto": texto,
            "categoria_id": cid,
            "subcategoria_id": sid,
            "fecha_registro_transaccion": str(fila["fecha_registro_transaccion"]),
        }
        if tid in documentos_por_id:
            if documentos_por_id[tid] != documento:
                raise DatosInvalidos("El historial contiene un movimiento duplicado y contradictorio.")
            excluidas["duplicados_identicos"] += 1
            continue
        documentos_por_id[tid] = documento

    # Orden estable para reproducir el resultado independientemente del orden SQL.
    # Se usa el instante consciente de zona, no se confunde TIMESTAMPTZ con DATE.
    documentos = sorted(
        documentos_por_id.values(),
        key=lambda f: (instante_con_zona(f["fecha_registro_transaccion"]), f["id_transaccion"]),
        reverse=True,
    )
    documentos_antes_limite = len(documentos)
    documentos = documentos[:CLASIFICADOR_PARAMETROS["max_documentos"]]
    etiquetas = [(f["categoria_id"], f["subcategoria_id"]) for f in documentos]
    clases = sorted(set(etiquetas), key=lambda par: (par[0], par[1] or ""))
    catalogo_huella = {
        "grupos": [grupos_por_id[k] for k in sorted(grupos_por_id)],
        "categorias": [categorias_por_id[k] for k in sorted(categorias_por_id)],
        "subcategorias": [subcategorias_por_id[k] for k in sorted(subcategorias_por_id)],
    }
    huella = hash_datos(
        contexto, "SUGERIR_CLASIFICACION",
        {"documentos": documentos, "catalogo": catalogo_huella, "consulta_normalizada": consulta},
        parametros={"version_clasificador": CLASIFICADOR_VERSION, **CLASIFICADOR_PARAMETROS},
    )
    ficha = {
        "version_clasificador": CLASIFICADOR_VERSION,
        "metodo": "SIN_SUGERENCIA",
        "documentos_elegibles": len(documentos),
        "documentos_antes_limite": documentos_antes_limite,
        "clases_elegibles": len(clases),
        "filas_excluidas": dict(sorted(excluidas.items())),
        "parametros": dict(CLASIFICADOR_PARAMETROS),
        "confianza_calibrada_disponible": False,
        "advertencia": "Los umbrales son reglas conservadoras versionadas, no precisión medida. La probabilidad Naive Bayes no está calibrada.",
        "confirmacion_requerida": True,
        "persistencia_prediccion": False,
    }

    def respuesta_sin_sugerencia(motivo, estado="SIN_SUGERENCIA"):
        respuesta = base_respuesta(contexto, estado, motivo, huella)
        respuesta.update({
            "detalle_consultado": detalle,
            "sugerencia_encontrada": False,
            "grupo_id": None, "categoria_id": None, "subcategoria_id": None,
            "codigo_grupo": None, "nombre_grupo": None,
            "nombre_categoria": None, "nombre_subcategoria": None,
            "confianza": None, "ficha_tecnica": ficha,
        })
        return respuesta

    def respuesta_sugerida(etiqueta, metodo):
        cid, sid = etiqueta
        categoria = categorias_por_id[cid]
        grupo = grupos_por_id[categoria["grupo_id"]]
        subcategoria = subcategorias_por_id[sid] if sid is not None else None
        ficha["metodo"] = metodo
        respuesta = base_respuesta(
            contexto, "OK", "Sugerencia basada en tu historial; confirma Aplicar.", huella,
        )
        respuesta.update({
            "detalle_consultado": detalle,
            "sugerencia_encontrada": True,
            "grupo_id": grupo["grupo_id"], "categoria_id": cid, "subcategoria_id": sid,
            "codigo_grupo": grupo["codigo_grupo"], "nombre_grupo": grupo["nombre_grupo"],
            "nombre_categoria": categoria["nombre_categoria"],
            "nombre_subcategoria": subcategoria["nombre_subcategoria"] if subcategoria else None,
            "confianza": None, "ficha_tecnica": ficha,
        })
        return respuesta

    if not categorias_por_id:
        return respuesta_sin_sugerencia("No tienes categorías activas elegibles para sugerir una clasificación.")
    if not documentos:
        return respuesta_sin_sugerencia("Aún no hay gastos propios con texto y clasificación vigentes para aprender.")

    coincidencias = Counter(
        etiqueta for fila, etiqueta in zip(documentos, etiquetas) if fila["texto"] == consulta
    )
    ficha["coincidencias_exactas"] = sum(coincidencias.values())
    if len(coincidencias) > 1:
        return respuesta_sin_sugerencia("Ese mismo detalle tiene clasificaciones distintas en tu historial; selecciona una manualmente.")
    if len(coincidencias) == 1:
        etiqueta, repeticiones = next(iter(coincidencias.items()))
        if repeticiones >= CLASIFICADOR_PARAMETROS["min_repeticiones_exactas"]:
            return respuesta_sugerida(etiqueta, "HISTORIAL_COINCIDENCIA")

    if len(documentos) < CLASIFICADOR_PARAMETROS["min_documentos_nb"] or len(clases) < CLASIFICADOR_PARAMETROS["min_clases_nb"]:
        return respuesta_sin_sugerencia("Todavía falta variedad de ejemplos para una sugerencia de texto nuevo; puedes clasificarlo manualmente.")

    vectorizador = TfidfVectorizer(
        lowercase=False, strip_accents=None, ngram_range=(1, 2),
        token_pattern=r"(?u)\b[a-z0-9]{2,}\b", stop_words=_CLAS_STOPWORDS,
        max_features=10000, norm="l2", dtype=np.float64,
    )
    try:
        matriz = vectorizador.fit_transform([f["texto"] for f in documentos])
    except ValueError as exc:
        if "empty vocabulary" not in str(exc).lower():
            raise
        return respuesta_sin_sugerencia("Los textos anteriores no contienen vocabulario suficiente para una sugerencia.")
    vector_consulta = vectorizador.transform([consulta])
    ficha["vocabulario_features"] = int(len(vectorizador.vocabulary_))
    if vector_consulta.nnz == 0:
        return respuesta_sin_sugerencia("El detalle no coincide con vocabulario aprendido de tus gastos; selecciona la clasificación manualmente.")

    # Comprobar evidencia léxica por clase además del posterior NB. Así el prior
    # de la clase mayoritaria no convierte una entrada desconocida en sugerencia.
    similitudes = (matriz @ vector_consulta.T).toarray().ravel()
    similares_por_clase = {clase: 0.0 for clase in clases}
    for etiqueta, similitud in zip(etiquetas, similitudes):
        similares_por_clase[etiqueta] = max(similares_por_clase[etiqueta], float(similitud))
    vecinas = sorted(similares_por_clase, key=lambda clase: (-similares_por_clase[clase], clase[0], clase[1] or ""))
    similitud_mejor = similares_por_clase[vecinas[0]]
    brecha_similitud = similitud_mejor - similares_por_clase[vecinas[1]]
    ficha["similitud_coseno_maxima"] = round(similitud_mejor, 6)
    ficha["brecha_similitud_clases"] = round(brecha_similitud, 6)
    if (similitud_mejor < CLASIFICADOR_PARAMETROS["min_similitud_coseno"]
            or brecha_similitud < CLASIFICADOR_PARAMETROS["min_brecha_similitud_clases"]):
        return respuesta_sin_sugerencia("La coincidencia con tus ejemplos no es suficientemente clara; selecciona la clasificación manualmente.")

    indices = {clase: i for i, clase in enumerate(clases)}
    modelo = MultinomialNB(alpha=CLASIFICADOR_PARAMETROS["alpha_nb"])
    modelo.fit(matriz, np.asarray([indices[etiqueta] for etiqueta in etiquetas], dtype=int))
    probabilidades = modelo.predict_proba(vector_consulta)[0]
    orden = np.argsort(-probabilidades, kind="stable")
    mejor_indice = int(modelo.classes_[int(orden[0])])
    probabilidad = float(probabilidades[int(orden[0])])
    margen = probabilidad - float(probabilidades[int(orden[1])])
    ficha["probabilidad_modelo_no_calibrada"] = round(probabilidad, 6)
    ficha["margen_probabilidades_no_calibradas"] = round(margen, 6)
    ficha["modelo_utilizado"] = "TfidfVectorizer + MultinomialNB"
    etiqueta = clases[mejor_indice]
    if (etiqueta != vecinas[0]
            or probabilidad < CLASIFICADOR_PARAMETROS["min_probabilidad_no_calibrada"]
            or margen < CLASIFICADOR_PARAMETROS["min_margen_probabilidades"]):
        return respuesta_sin_sugerencia("El modelo no obtuvo evidencia suficientemente separada entre tus clasificaciones; elige una manualmente.")
    return respuesta_sugerida(etiqueta, "TFIDF_MULTINOMIAL_NB_PRIVADO")



class MotorConCache:
    """Caché acotada por proceso, creada explícitamente por FastAPI al arrancar.

    Siempre cargar/autorizar una instantánea propia antes de consultar la caché.
    No contiene conexiones SQL. El candado evita duplicar el cómputo simultáneo;
    su límite de 32 entradas no es una promesa de rendimiento ni durabilidad.
    """
    def __init__(self, max_entradas=32):
        from collections import OrderedDict
        from threading import RLock
        if isinstance(max_entradas, bool) or not isinstance(max_entradas, int) or max_entradas < 1:
            raise DatosInvalidos("max_entradas debe ser un entero positivo")
        self._limite = max_entradas
        self._cache = OrderedDict()
        self._lock = RLock()

    def _calcular(self, clave, contexto, funcion, forzar=False):
        from copy import deepcopy
        with self._lock:
            reutilizado = not forzar and clave in self._cache
            if reutilizado:
                original = self._cache.pop(clave)
                self._cache[clave] = original
            else:
                original = respuesta_json(funcion())
                self._cache[clave] = deepcopy(original)
                while len(self._cache) > self._limite:
                    self._cache.popitem(last=False)
            salida = deepcopy(original)
        # La nueva instantánea verificó que las entradas relevantes no cambiaron.
        # Actualizar el corte de comprobación NO equivale a entrenar otra vez.
        salida.update(fecha_corte_datos=contexto.fecha_corte_datos.isoformat(),
                      fecha_generacion_prediccion=contexto.fecha_generacion.isoformat(),
                      contexto_analitico=sello_contexto(contexto))
        for campo in ("proyeccion_periodo",):
            if isinstance(salida.get(campo), dict):
                salida[campo]["fecha_corte_datos"] = contexto.fecha_corte_datos.isoformat()
        salida["cache_precomputo"] = {"reutilizado": reutilizado, "clave": clave,
                                     "fecha_calculo_original": original["fecha_generacion_prediccion"],
                                     "alcance": "RAM acotada del proceso; validar entradas antes de reutilizar"}
        return salida

    def pronostico(self, movimientos, contexto, *, cobertura, grupo_id=None, grupos=(), forzar=False):
        gid = _pron_grupo_propio(grupo_id, grupos, contexto)
        intervalos = _pron_cobertura(cobertura, contexto)
        ultimo_domingo = contexto.fecha_local-timedelta(days=contexto.fecha_local.weekday()+1)
        desde = ultimo_domingo-timedelta(days=7*104-1)
        propias = filas_propias(movimientos, contexto, campos=("id_transaccion", "fecha_operacion_transaccion", "fecha_registro_transaccion", "gasto_conocido", "grupo_id"))
        cerradas = [{k:r[k] for k in ("id_transaccion", "fecha_operacion_transaccion", "fecha_registro_transaccion", "gasto_conocido", "grupo_id")}
                    for r in propias if desde<=fecha_local_valor(r["fecha_operacion_transaccion"])<=ultimo_domingo
                    and (gid is None or (r.get("grupo_id") is not None and normalizar_uuid(r["grupo_id"])==gid))]
        conocida = [(max(inicio,desde),min(fin,ultimo_domingo)) for inicio,fin in intervalos if inicio<=ultimo_domingo and fin>=desde]
        clave = hash_datos(contexto,"CACHE_PRONOSTICO",cerradas,
                           {"grupo_id":gid,"cobertura":conocida,"ultimo_domingo":ultimo_domingo})
        return self._calcular(clave, contexto,
                              lambda: ejecutar_pronostico_semanal(propias, contexto, cobertura=cobertura, grupo_id=gid, grupos=grupos), forzar)

    def clustering(self, transacciones, contexto, *, periodo=None, forzar=False):
        propias = filas_propias(transacciones, contexto)
        pid = normalizar_uuid(periodo["id_periodo"]) if periodo is not None else None
        seleccion = [r for r in propias if r.get("tipo_transaccion")=="GASTO" and r.get("periodo_id") is not None and normalizar_uuid(r["periodo_id"])==pid]
        clave = hash_datos(contexto,"CACHE_CLUSTER",seleccion,{"periodo":periodo,"dia":contexto.fecha_local})
        return self._calcular(clave, contexto, lambda: ejecutar_clustering_hormiga(propias,contexto,periodo=periodo),forzar)

    def salud(self, resumen_periodo, detalles_grupo, contexto, *, pronostico=None, forzar=False):
        detalles = registros(detalles_grupo)
        # La salud completa sólo utiliza tendencia de un pronóstico global
        # compatible con ESTE contexto. Huella/estado por sí solos no distinguen
        # un pronóstico anterior cuyo sello/corte ya no es válido. A la vez, no
        # meter el reloj del corte en la clave evita recomputar una tendencia
        # igual cuando el backend comprobó una nueva instantánea compatible.
        tendencia = {"compatible": False}
        if isinstance(pronostico, dict) and pronostico.get("estado") == "OK":
            corte_pronostico = pronostico.get("fecha_corte_datos")
            mismo_corte = corte_pronostico is not None and _per_instante(
                corte_pronostico, "fecha_corte_datos del pronóstico") == contexto.fecha_corte_datos
            compatible = (
                pronostico.get("origen_datos") == contexto.origen_datos
                and pronostico.get("grupo_id") is None
                and mismo_corte
                and pronostico.get("contexto_analitico") == sello_contexto(contexto)
                and bool(pronostico.get("version_modelo"))
                and pronostico.get("pendiente_semanal") is not None)
            if compatible:
                tendencia = {
                    "compatible": True,
                    "huella_datos": pronostico.get("huella_datos"),
                    "pendiente_semanal": decimal_finito(pronostico["pendiente_semanal"], "pendiente_semanal"),
                    "version_modelo": pronostico["version_modelo"],
                    "grupo_id": None}
        clave = hash_datos(contexto,"CACHE_SALUD",{"periodo":resumen_periodo,"detalles":detalles},
                           {"dia":contexto.fecha_local,"tendencia":tendencia})
        return self._calcular(clave,contexto,lambda: evaluar_salud_difusa_periodo(resumen_periodo,detalles,contexto,pronostico=pronostico),forzar)

    def limpiar(self):
        with self._lock:
            self._cache.clear()




def construir_registro_prediccion(resultado, contexto):
    """Mapea un resultado INTERNO exitoso a las 25 entradas reales de PREDICCION.

    No ejecuta SQL. Nunca aceptar este resultado desde una petición del cliente.
    ID y generación los asigna el trigger. Los estados insuficientes y las
    proyecciones/sugerencias devuelven None, no filas con valores falsos.
    """
    if not isinstance(resultado, dict):
        raise DatosInvalidos("Se requiere un resultado interno del motor")
    if resultado.get("estado") != "OK":
        return None
    tipo = resultado.get("tipo_prediccion")
    if tipo not in ("SEMANAL_GLOBAL", "SEMANAL_GRUPO", "KMEANS_HORMIGA", "SALUD_DIFUSA"):
        return None
    if resultado.get("contexto_analitico") != sello_contexto(contexto):
        raise DatosInvalidos("El resultado no corresponde al contexto confiable")
    if resultado.get("origen_datos") != contexto.origen_datos:
        raise DatosInvalidos("Procedencia incompatible")
    if instante_con_zona(resultado.get("fecha_corte_datos")) != contexto.fecha_corte_datos:
        raise DatosInvalidos("El corte del resultado no corresponde al contexto")
    respuesta = respuesta_json(resultado)
    ficha = respuesta.get("ficha_tecnica")
    if not isinstance(ficha, dict):
        raise DatosInvalidos("Un resultado persistible requiere ficha_tecnica")
    version = respuesta.get("version_modelo")
    if not isinstance(version, str) or not 1 <= len(version.strip()) <= 50 or version != version.strip():
        raise DatosInvalidos("Versión de modelo inválida")
    modelo = ficha.get("modelo_utilizado")
    if not isinstance(modelo, str) or not 1 <= len(modelo.strip()) <= 100 or modelo != modelo.strip():
        raise DatosInvalidos("Identificador de modelo inválido")
    huella = respuesta.get("huella_datos")
    if not isinstance(huella, str) or re.fullmatch(r"[0-9a-f]{64}", huella) is None:
        raise DatosInvalidos("Falta la huella SHA-256 del resultado")
    explicacion = respuesta.get("explicacion_ux")
    if not isinstance(explicacion, str) or not explicacion.strip():
        raise DatosInvalidos("Falta explicación del resultado")

    def fecha(campo):
        valor = ficha.get(campo, respuesta.get(campo))
        if valor is None:
            raise DatosInvalidos(f"Falta {campo} para persistir el resultado")
        return fecha_local_valor(valor)

    inicio, fin = fecha("periodo_inicio_historial"), fecha("periodo_fin_historial")
    if inicio > fin or fin > contexto.fecha_local:
        raise DatosInvalidos("Rango histórico incompatible con el corte")
    grupo = respuesta.get("grupo_id", ficha.get("grupo_id"))
    periodo = respuesta.get("periodo_id", ficha.get("periodo_id"))
    grupo = normalizar_uuid(grupo, "grupo_id") if grupo is not None else None
    periodo = normalizar_uuid(periodo, "periodo_id") if periodo is not None else None
    fila = {"usuario_id": contexto.usuario_id, "grupo_id": grupo, "periodo_id": periodo,
            "tipo_prediccion": tipo, "fecha_corte_datos": contexto.fecha_corte_datos,
            "periodo_inicio_historial": inicio, "periodo_fin_historial": fin,
            "periodo_inicio_objetivo": None, "periodo_fin_objetivo": None,
            "gasto_estimado_prediccion": None, "rango_min_estimado": None,
            "rango_max_estimado": None, "pendiente_tendencia_semanal": None,
            "score_salud_difuso": None, "nivel_confiabilidad_ux": None,
            "modelo_utilizado": modelo, "version_modelo": version,
            "semanas_completas_utilizadas": None, "origen_datos": contexto.origen_datos,
            "huella_datos": huella, "mae_modelo": None, "mae_naive_base": None,
            "rmse_modelo": None, "r2_modelo": None, "metadatos_modelo": None}
    meta = {"estado": "OK", "tipo_prediccion": tipo, "origen_datos": contexto.origen_datos,
            "huella_datos": huella, "zona_horaria": "America/Mexico_City",
            "explicacion_ux": explicacion, "ficha_tecnica": ficha, "respuesta_api": respuesta}
    if tipo in ("SEMANAL_GLOBAL", "SEMANAL_GRUPO"):
        if (tipo == "SEMANAL_GLOBAL" and grupo is not None) or (tipo == "SEMANAL_GRUPO" and grupo is None):
            raise DatosInvalidos("Contexto de grupo incompatible con la regresión")
        n = ficha.get("semanas_completas_utilizadas")
        if isinstance(n, bool) or not isinstance(n, int) or n < 8 or ficha.get("cobertura_conocida") is not True:
            raise DatosInvalidos("No hay ocho semanas completas de cobertura conocida")
        obj_inicio, obj_fin = fecha("periodo_inicio_objetivo"), fecha("periodo_fin_objetivo")
        if (inicio.weekday() != 0 or fin.weekday() != 6 or (fin-inicio).days+1 != 7*n
                or fin >= contexto.fecha_local or obj_inicio != fin+timedelta(days=1)
                or obj_fin != obj_inicio+timedelta(days=6)):
            raise DatosInvalidos("Semanas u objetivo incompatibles con la restricción SQL")
        def metrica(campo):
            x = decimal_finito(ficha.get(campo), campo)
            if x < 0:
                raise DatosInvalidos(f"{campo} no puede ser negativo")
            return x
        mae, naive, rmse = (metrica(c) for c in ("mae_modelo", "mae_naive_base", "rmse_modelo"))
        pred = Decimal(moneda(respuesta.get("gasto_estimado")))
        bajo, alto = Decimal(moneda(max(0, pred-mae))), Decimal(moneda(pred+mae))
        if min(pred, bajo) < 0 or max(pred, alto) > MAX_MONTO_SQL:
            raise DatosInvalidos("Resultado fuera de NUMERIC(12,2)")
        if bajo != decimal_finito(respuesta.get("rango_min_ux")) or alto != decimal_finito(respuesta.get("rango_max_ux")):
            raise DatosInvalidos("La banda no coincide con predicción ± MAE persistido")
        nivel = respuesta.get("nivel_confiabilidad_ux")
        if nivel not in ("ALTA", "MEDIA", "BAJA"):
            raise DatosInvalidos("Indicador de confiabilidad inválido")
        r2 = ficha.get("r2_modelo")
        if r2 is not None:
            r2 = float(decimal_finito(r2, "r2_modelo"))
            if not math.isfinite(r2) or r2 > 1:
                raise DatosInvalidos("R² inválido")
        fila.update(periodo_inicio_objetivo=obj_inicio, periodo_fin_objetivo=obj_fin,
                    gasto_estimado_prediccion=pred, rango_min_estimado=bajo, rango_max_estimado=alto,
                    pendiente_tendencia_semanal=decimal_finito(respuesta.get("pendiente_semanal")),
                    nivel_confiabilidad_ux=nivel, semanas_completas_utilizadas=n,
                    mae_modelo=mae, mae_naive_base=naive, rmse_modelo=rmse, r2_modelo=r2)
        meta.update(cobertura_conocida=True, cobertura=ficha.get("cobertura", {}), semanas_completas_utilizadas=n)
    else:
        if periodo is None or grupo is not None:
            raise DatosInvalidos("K-Means y salud requieren periodo propio, sin grupo")
        if tipo == "SALUD_DIFUSA":
            score = decimal_finito(respuesta.get("score_salud_difuso"), "score_salud_difuso")
            if not 0 <= score <= 100:
                raise DatosInvalidos("Score fuera de 0..100")
            fila["score_salud_difuso"] = score
            meta["score_salud_difuso"] = float(score)
    fila["metadatos_modelo"] = respuesta_json(meta)
    return fila


__all__ = ["ContextoAnalitico", "DatosInvalidos", "VERSION_MOTOR",
           "ejecutar_pronostico_semanal", "ejecutar_clustering_hormiga",
           "evaluar_salud_difusa_periodo", "sugerir_clasificacion_texto",
           "proyectar_periodo", "proyectar_meta", "construir_registro_prediccion",
           "respuesta_json", "MotorConCache"]
