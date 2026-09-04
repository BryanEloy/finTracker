from sqlalchemy import Boolean, Column, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Usuario(Base):
    __tablename__ = "usuario"

    id_usuario = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    nombre_usuario = Column(
        String(100),
        nullable=False,
    )

    correo_usuario = Column(
        String(254),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash_usuario = Column(
        String(255),
        nullable=False,
    )

    ruta_foto_perfil_local_usuario = Column(
        String(255),
        nullable=True,
    )

    notificaciones_presupuesto = Column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    notificaciones_periodicas = Column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    fecha_registro_usuario = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    es_activo_usuario = Column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    fecha_desactivacion_usuario = Column(
        DateTime(timezone=True),
        nullable=True,
    )