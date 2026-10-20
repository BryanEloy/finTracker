from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


# Consultas explícitas: naturaleza_grupo es un enum PostgreSQL.
# Su conversión a texto evita depender de la definición del enum en Python.
_SELECT = """
    SELECT id_grupo, codigo_grupo, nombre_grupo,
           naturaleza_grupo::text AS naturaleza_grupo,
           porcentaje_sugerido_grupo, es_activo_grupo
    FROM public.grupo
    WHERE usuario_id = :usuario_id
"""


def listar_grupos(db: Session, usuario_id: UUID) -> list[dict]:
    filas = db.execute(
        text(_SELECT + " ORDER BY codigo_grupo"),
        {"usuario_id": usuario_id},
    ).mappings().all()
    return [dict(fila) for fila in filas]


def obtener_grupo_por_id(db: Session, usuario_id: UUID, id_grupo: UUID) -> dict | None:
    fila = db.execute(
        text(_SELECT + " AND id_grupo = :id_grupo"),
        {"usuario_id": usuario_id, "id_grupo": id_grupo},
    ).mappings().one_or_none()
    return dict(fila) if fila is not None else None
