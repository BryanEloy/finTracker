"""Cableado conservador FinTrack V1.1; no modifica saldos ni guarda predicciones."""
from uuid import UUID

import psycopg
from fastapi import Depends
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.modules.usuarios.model import Usuario
from app.modules.analitica.ejemplo_integracion_fastapi import crear_router


def usuario_activo_uuid(usuario: Usuario = Depends(get_current_user)) -> UUID:
    """La dependencia actual verifica JWT y estado activo en BD."""
    return usuario.id_usuario


def conexion_factory():
    """Conexión psycopg exclusiva e IDLE para cada instantánea; nunca Session SQLAlchemy."""
    url = make_url(settings.DATABASE_URL)
    if not url.drivername.startswith('postgresql'):
        raise RuntimeError('La analítica requiere PostgreSQL')
    # El motor psycopg no acepta la sintaxis dialecto+driver de SQLAlchemy.
    return psycopg.connect(url.set(drivername='postgresql').render_as_string(hide_password=False))


def politica_datos(usuario_id, instantanea):
    """Política segura inicial: usuarios reales y cobertura NO certificada.

    No inferir semanas cubiertas por fecha de registro o primer movimiento.
    Para una DEMO sintética, implementar autorización/certificación del lado servidor
    y aislar completamente los datos de producción antes de modificar esta política.
    """
    return {'origen_datos': 'REAL', 'cobertura': []}


router = crear_router(
    usuario_activo_uuid,
    conexion_factory,
    politica_datos,
    persistir_resultados=False,
)
