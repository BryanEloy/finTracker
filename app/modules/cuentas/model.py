from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from app.db.base import Base


class TipoCuenta(str, Enum):
    EFECTIVO = "EFECTIVO"
    DEBITO = "DEBITO"
    AHORRO = "AHORRO"
    CREDITO = "CREDITO"


class Cuenta(Base):
    __tablename__ = "cuenta"

    id_cuenta = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id_usuario", ondelete="RESTRICT"),
        nullable=False,
    )

    nombre_cuenta = Column(
        String(100),
        nullable=False,
    )

    tipo_cuenta = Column(
        PGEnum(
            TipoCuenta,
            name="tipo_cuenta_enum",
            create_type=False,
        ),
        nullable=False,
    )

    institucion_cuenta = Column(
        String(100),
        nullable=True,
    )

    numero_cuenta = Column(
        String(30),
        nullable=True,
    )

    es_activa_cuenta = Column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    fecha_creacion_cuenta = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    saldo_inicial_cuenta = Column(
        Numeric(12, 2),
        nullable=False,
    )

    limite_credito_cuenta = Column(
        Numeric(12, 2),
        nullable=True,
    )