from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from app.db.base import Base


class TipoTransaccion(str, Enum):
    INGRESO = "INGRESO"
    GASTO = "GASTO"
    TRANSFERENCIA = "TRANSFERENCIA"


class Transaccion(Base):
    __tablename__ = "transaccion"

    id_transaccion = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "usuario.id_usuario",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    cuenta_id = Column(
        UUID(as_uuid=True),
        nullable=False,
    )

    tipo_transaccion = Column(
        PGEnum(
            TipoTransaccion,
            name="tipo_transaccion_enum",
            create_type=False,
        ),
        nullable=False,
    )

    cuenta_destino_id = Column(
        UUID(as_uuid=True),
        nullable=True,
    )

    categoria_id = Column(
        UUID(as_uuid=True),
        nullable=True,
    )

    subcategoria_id = Column(
        UUID(as_uuid=True),
        nullable=True,
    )

    monto_transaccion = Column(
        Numeric(12, 2),
        nullable=False,
    )

    fecha_registro_transaccion = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    comentario_transaccion = Column(
        String(500),
        nullable=True,
    )