from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
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
            name="fk_transaccion_usuario",
        ),
        nullable=False,
    )

    cuenta_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "cuenta.id_cuenta",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
            name="fk_transaccion_cuenta",
        ),
        nullable=False,
    )

    cuenta_destino_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "cuenta.id_cuenta",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
            name="fk_transaccion_cuenta_destino",
        ),
        nullable=True,
    )

    tipo_transaccion = Column(
        PGEnum(
            TipoTransaccion,
            name="tipo_transaccion_enum",
        ),
        nullable=False,
    )

    categoria_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "categoria.id_categoria",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
            name="fk_transaccion_categoria",
        ),
        nullable=True,
    )

    subcategoria_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "subcategoria.id_subcategoria",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
            name="fk_transaccion_subcategoria",
        ),
        nullable=True,
    )

    monto_transaccion = Column(
        Numeric(12, 2),
        nullable=False,
    )

    fecha_transaccion = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    fecha_registro_transaccion = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    comentario_transaccion = Column(
        String(500),
        nullable=True,
    )

    __table_args__ = (
        # TRA-02
        CheckConstraint(
            "monto_transaccion > 0",
            name="ck_transaccion_monto",
        ),

        # TRA-05 y TRA-07
        CheckConstraint(
            """
            (
                tipo_transaccion = 'TRANSFERENCIA'
                AND cuenta_destino_id IS NOT NULL
                AND cuenta_id <> cuenta_destino_id
            )
            OR
            (
                tipo_transaccion <> 'TRANSFERENCIA'
                AND cuenta_destino_id IS NULL
            )
            """,
            name="ck_transaccion_cuenta_destino",
        ),

        # TRA-03, TRA-04 y TRA-06
        CheckConstraint(
            """
            (
                tipo_transaccion = 'GASTO'
                AND categoria_id IS NOT NULL
            )
            OR
            (
                tipo_transaccion IN ('INGRESO', 'TRANSFERENCIA')
                AND categoria_id IS NULL
                AND subcategoria_id IS NULL
            )
            """,
            name="ck_transaccion_categoria",
        ),

        # Una subcategoría nunca existe sin categoría.
        CheckConstraint(
            """
            subcategoria_id IS NULL
            OR categoria_id IS NOT NULL
            """,
            name="ck_transaccion_subcategoria",
        ),

        # TRA-30
        CheckConstraint(
            """
            comentario_transaccion IS NULL
            OR (
                comentario_transaccion = BTRIM(comentario_transaccion)
                AND CHAR_LENGTH(comentario_transaccion)
                    BETWEEN 1 AND 500
            )
            """,
            name="ck_transaccion_comentario",
        ),

        Index(
            "ix_transaccion_usuario_fecha",
            "usuario_id",
            text("fecha_transaccion DESC"),
            text("fecha_registro_transaccion DESC"),
        ),

        Index(
            "ix_transaccion_usuario_tipo",
            "usuario_id",
            "tipo_transaccion",
        ),

        Index(
            "ix_transaccion_usuario_cuenta",
            "usuario_id",
            "cuenta_id",
        ),

        Index(
            "ix_transaccion_usuario_cuenta_destino",
            "usuario_id",
            "cuenta_destino_id",
        ),

        Index(
            "ix_transaccion_usuario_categoria",
            "usuario_id",
            "categoria_id",
        ),
    )