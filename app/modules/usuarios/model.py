import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    String,
    text
)

from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Usuario(Base):

    __tablename__ = "usuarios"

    id_usuario = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    nombre_usuario = Column(
        String(100),
        nullable=False
    )

    correo_usuario = Column(
        String(254),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = Column(
        String(255),
        nullable=False
    )

    avatar_codigo = Column(
        String(50),
        nullable=False,
        default="default_01"
    )

    notificaciones_presupuesto = Column(
        Boolean,
        nullable=False,
        default=True
    )

    es_activo = Column(
        Boolean,
        nullable=False,
        default=True
    )

    fecha_registro_usuario = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()")
    )

    ultimo_acceso_usuario = Column(
        DateTime(timezone=True),
        nullable=True
    )

    fecha_desactivacion_usuario = Column(
        DateTime(timezone=True),
        nullable=True
    )