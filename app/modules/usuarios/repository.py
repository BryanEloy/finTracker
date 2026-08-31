from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.usuarios.model import Usuario


def obtener_por_id(
    db: Session,
    id_usuario: UUID
) -> Usuario | None:
    return db.scalar(
        select(Usuario).where(
            Usuario.id_usuario == id_usuario
        )
    )


def obtener_por_correo(
    db: Session,
    correo_usuario: str
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
    password_hash: str,
    avatar_codigo: str = "default_01",
) -> Usuario:
    usuario = Usuario(
        nombre_usuario=nombre_usuario,
        correo_usuario=correo_usuario,
        password_hash=password_hash,
        avatar_codigo=avatar_codigo,
    )

    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return usuario


def actualizar(
    db: Session,
    usuario: Usuario,
    *,
    nombre_usuario: str | None = None,
    avatar_codigo: str | None = None,
    notificaciones_presupuesto: bool | None = None,
) -> Usuario:
    if nombre_usuario is not None:
        usuario.nombre_usuario = nombre_usuario

    if avatar_codigo is not None:
        usuario.avatar_codigo = avatar_codigo

    if notificaciones_presupuesto is not None:
        usuario.notificaciones_presupuesto = (
            notificaciones_presupuesto
        )

    db.commit()
    db.refresh(usuario)

    return usuario


def actualizar_password(
    db: Session,
    usuario: Usuario,
    password_hash: str
) -> None:
    usuario.password_hash = password_hash

    db.commit()


def actualizar_ultimo_acceso(
    db: Session,
    usuario: Usuario
) -> Usuario:
    usuario.ultimo_acceso_usuario = datetime.now(timezone.utc)

    db.commit()
    db.refresh(usuario)

    return usuario


def desactivar(
    db: Session,
    usuario: Usuario
) -> None:
    usuario.es_activo = False
    usuario.fecha_desactivacion_usuario = datetime.now(timezone.utc)

    db.commit()