"""FinTrack V1.1: política certificada, PNG bajo demanda y reportes de lectura."""
import os
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.modules.usuarios.model import Usuario
from app.modules.analitica.ejemplo_integracion_fastapi import crear_router
from app.modules.analitica.politica_datos import crear_politica_datos
from app.modules.analitica.reportes_periodo import crear_router_reportes


def usuario_activo_uuid(usuario: Usuario = Depends(get_current_user)) -> UUID:
    """La dependencia actual verifica JWT y estado activo en BD."""
    return usuario.id_usuario


def conexion_factory():
    """Conexión psycopg exclusiva e IDLE para cada instantánea; nunca Session SQLAlchemy."""
    url = make_url(settings.DATABASE_URL)
    if not url.drivername.startswith('postgresql'):
        raise RuntimeError('La analítica requiere PostgreSQL')
    # El motor psycopg no acepta la sintaxis dialecto+driver de SQLAlchemy.
    return psycopg.connect(
        url.set(drivername='postgresql').render_as_string(hide_password=False),
        connect_timeout=10,
        application_name="fintrack-analitica-v11",
    )


_politica_certificada = crear_politica_datos(
    conexion_factory,
    cobertura_real_json=os.getenv("FINTRACK_COBERTURA_REAL_JSON", "{}"),
)


def politica_datos(usuario_id, instantanea):
    """Obtiene procedencia y cobertura certificadas desde la política V1.1.1."""
    return _politica_certificada(usuario_id, instantanea)


router = APIRouter()
router.include_router(crear_router(
    usuario_activo_uuid,
    conexion_factory,
    politica_datos,
    persistir_resultados=False,
))

# main.py ya incluye este router: no registrar rutas analíticas dos veces.
router.include_router(crear_router_reportes(usuario_activo_uuid, conexion_factory))
