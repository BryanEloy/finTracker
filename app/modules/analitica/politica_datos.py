"""Procedencia/cobertura por UUID; solo SELECT, nunca escribe o inventa fechas."""
from __future__ import annotations

import json
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg

from app.modules.analitica.adaptador_neon_v11 import ErrorAdaptador


DATASET_DEMO = "FINTRACK_DEMO_20261021_R1"
ZONA_LOCAL = ZoneInfo("America/Mexico_City")


def _configuracion_real(texto):
    """Configuración privada del servidor, no parámetro de la API ni del JWT."""
    try:
        if not isinstance(texto, str) or len(texto.encode("utf-8")) > 65536:
            raise ValueError("Configuración demasiado grande")
        datos = json.loads(texto)
        if not isinstance(datos, dict) or len(datos) > 256:
            raise ValueError("Se requiere objeto UUID -> intervalos")
        salida = {}
        for usuario, intervalos in datos.items():
            uid = str(UUID(usuario))
            if uid in salida or not isinstance(intervalos, list) or len(intervalos) > 32:
                raise ValueError("Intervalos inválidos")
            certificados = []
            for intervalo in intervalos:
                if not isinstance(intervalo, dict) or set(intervalo) != {"fecha_inicio", "fecha_fin"}:
                    raise ValueError("Solo se admiten fecha_inicio y fecha_fin")
                inicio = date.fromisoformat(intervalo["fecha_inicio"])
                fin = date.fromisoformat(intervalo["fecha_fin"])
                if inicio > fin:
                    raise ValueError("Intervalo invertido")
                certificados.append((inicio, fin))
            salida[uid] = certificados
        return salida
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("FINTRACK_COBERTURA_REAL_JSON inválido; revisar configuración privada") from exc


def crear_politica_datos(conexion_factory, *, cobertura_real_json="{}"):
    """Construir una vez al arrancar. No abre conexiones durante el import.

    Un DEMO se certifica mediante el registro SQL existente. Un usuario real sin
    certificación explícita conserva REAL + []; su pronóstico puede ser insuficiente.
    La configuración de cobertura real debe autorizarse tras revisar sus registros.
    """
    reales = _configuracion_real(cobertura_real_json)

    def politica_datos(usuario_id, instantanea):
        try:
            uid = UUID(str(usuario_id))
            if UUID(str(instantanea["usuario_id"])) != uid:
                raise ValueError("Propietario distinto")
            corte = instantanea["fecha_corte_datos"]
            if isinstance(corte, str):
                corte = datetime.fromisoformat(corte.replace("Z", "+00:00"))
            if not isinstance(corte, datetime) or corte.tzinfo is None:
                raise ValueError("Corte sin zona")
            hoy = corte.astimezone(ZONA_LOCAL).date()
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ErrorAdaptador("Instantánea incompatible con la política de datos") from exc

        try:
            with conexion_factory() as conn:
                conn.read_only = True
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT origen_datos, fecha_inicio_cobertura,
                                  fecha_fin_cobertura, codigo_dataset, fecha_carga
                           FROM public.fintrack_demo_dataset_v11
                           WHERE usuario_id = %s""",
                        (uid,),
                    )
                    demo = cur.fetchone()
        except psycopg.Error as exc:
            # No ocultar tabla ausente o falta de SELECT como si fuera un usuario real.
            raise ErrorAdaptador("No se pudo verificar el registro de procedencia DEMO") from exc

        intervalos = reales.get(str(uid), [])
        origen = "REAL"
        if demo is not None:
            origen, inicio, fin, codigo, fecha_carga = demo
            if (origen != "SINTETICO" or codigo != DATASET_DEMO or str(uid) in reales
                    or not isinstance(inicio, date) or not isinstance(fin, date)
                    or isinstance(inicio, datetime) or isinstance(fin, datetime)
                    or inicio > fin or fin > hoy or fecha_carga > corte):
                raise ErrorAdaptador("Certificación DEMO inválida o posterior al corte")
            intervalos = [(inicio, fin)]
        if any(fin > hoy for _, fin in intervalos):
            raise ErrorAdaptador("La cobertura real no puede certificar fechas futuras")

        return {
            "origen_datos": origen,
            "cobertura": [{"usuario_id": str(uid), "fecha_inicio": inicio.isoformat(),
                           "fecha_fin": fin.isoformat()} for inicio, fin in intervalos],
        }

    return politica_datos
