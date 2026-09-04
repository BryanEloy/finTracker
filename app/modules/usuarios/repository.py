from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.usuarios.model import Usuario


def obtener_por_id(
    db: Session,
    id_usuario: UUID,
) -> Usuario | None:

    return db.scalar(
        select(Usuario).where(
            Usuario.id_usuario == id_usuario
        )
    )


def obtener_por_correo(
    db: Session,
    correo_usuario: str,
) -> Usuario | None:

    return db.scalar(
        select(Usuario).where(
            Usuario.correo_usuario == correo_usuario
        )
    )


def crear(
    db: Session,
    *,
    nombre_usuario: str,
    correo_usuario: str,
    password_hash_usuario: str,
) -> Usuario:

    usuario = Usuario(
        nombre_usuario=nombre_usuario,
        correo_usuario=correo_usuario,
        password_hash_usuario=password_hash_usuario,
    )

    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return usuario


def actualizar(
    db: Session,
    usuario: Usuario,
    cambios: dict,
) -> Usuario:

    for campo, valor in cambios.items():
        setattr(
            usuario,
            campo,
            valor,
        )

    db.commit()
    db.refresh(usuario)

    return usuario


def actualizar_password(
    db: Session,
    usuario: Usuario,
    password_hash_usuario: str,
) -> None:

    usuario.password_hash_usuario = (
        password_hash_usuario
    )

    db.commit()


def desactivar(
    db: Session,
    usuario: Usuario,
) -> None:

    usuario.es_activo_usuario = False

    usuario.fecha_desactivacion_usuario = (
        datetime.now(timezone.utc)
    )

    db.commit()