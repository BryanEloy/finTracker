from enum import Enum

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from app.db.base import Base


# ============================================================
# ENUMS
# ============================================================

class EstadoMeta(str, Enum):
    ACTIVA = "ACTIVA"
    CANCELADA = "CANCELADA"
    ALCANZADA = "ALCANZADA"
    NO_ALCANZADA = "NO_ALCANZADA"


class TipoAsignacion(str, Enum):
    APORTE = "APORTE"
    RETIRO = "RETIRO"


# ============================================================
# META
# ============================================================

class Meta(Base):
    __tablename__ = "meta"

    id_meta = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    usuario_id = Column(
        UUID(as_uuid=True),
        nullable=False,
    )

    cuenta_id = Column(
        UUID(as_uuid=True),
        nullable=False,
    )

    nombre_meta = Column(
        String(100),
        nullable=False,
    )

    monto_objetivo_meta = Column(
        Numeric(12, 2),
        nullable=False,
    )

    fecha_limite_meta = Column(
        Date,
        nullable=False,
    )

    fecha_creacion_meta = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    fecha_cierre_meta = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    estado_meta = Column(
        PGEnum(
            EstadoMeta,
            name="estado_meta_enum",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'ACTIVA'::estado_meta_enum"),
    )

    descripcion_meta = Column(
        String(500),
        nullable=True,
    )


# ============================================================
# ASIGNACION_META
# ============================================================

class AsignacionMeta(Base):
    __tablename__ = "asignacion_meta"

    id_asignacion = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    meta_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "meta.id_meta",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    tipo_asignacion = Column(
        PGEnum(
            TipoAsignacion,
            name="tipo_asignacion_enum",
            create_type=False,
        ),
        nullable=False,
    )

    monto_asignacion = Column(
        Numeric(12, 2),
        nullable=False,
    )

    fecha_registro_asignacion = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    comentario_asignacion = Column(
        String(500),
        nullable=True,
    )