from enum import Enum

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Numeric,
    SmallInteger,
    text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from app.db.base import Base


class EstadoPresupuesto(str, Enum):
    ACTIVO = "ACTIVO"
    FINALIZADO = "FINALIZADO"
    CANCELADO = "CANCELADO"


class Presupuesto(Base):
    __tablename__ = "presupuesto"

    id_presupuesto = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    usuario_id = Column(
        UUID(as_uuid=True),
        nullable=False,
    )

    fecha_inicio_presupuesto = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    fecha_fin_presupuesto = Column(
        Date,
        nullable=False,
    )

    fecha_cierre_presupuesto = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    estado_presupuesto = Column(
        PGEnum(
            EstadoPresupuesto,
            name="estado_presupuesto_enum",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'ACTIVO'::estado_presupuesto_enum"),
    )

    monto_limite_presupuesto = Column(
        Numeric(12, 2),
        nullable=False,
    )


class DetallePresupuesto(Base):
    __tablename__ = "detalle_presupuesto"

    id_detalle_presupuesto = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    presupuesto_id = Column(
        UUID(as_uuid=True),
        nullable=False,
    )

    usuario_id = Column(
        UUID(as_uuid=True),
        nullable=False,
    )

    categoria_id = Column(
        UUID(as_uuid=True),
        nullable=False,
    )

    porcentaje_asignado_presupuesto = Column(
        SmallInteger,
        nullable=False,
    )

    porcentaje_alerta_presupuesto = Column(
        SmallInteger,
        nullable=False,
        server_default=text("80"),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["usuario_id", "presupuesto_id"],
            ["presupuesto.usuario_id", "presupuesto.id_presupuesto"],
            name="fk_detalle_presupuesto_propietario",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["usuario_id", "categoria_id"],
            ["categoria.usuario_id", "categoria.id_categoria"],
            name="fk_detalle_presupuesto_categoria_propietario",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )