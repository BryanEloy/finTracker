from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from app.modules.grupos.model import Grupo

from app.db.base import Base


class Categoria(Base):
    __tablename__ = "categoria"
    __table_args__ = (
        ForeignKeyConstraint(
            ["usuario_id", "grupo_id"],
            ["grupo.usuario_id", "grupo.id_grupo"],
            name="fk_categoria_grupo_usuario",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )

    id_categoria = Column(
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

    nombre_categoria = Column(
        String(100),
        nullable=False,
    )

    es_activa_categoria = Column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )


    grupo_id = Column(UUID(as_uuid=True), nullable=False)


class Subcategoria(Base):
    __tablename__ = "subcategoria"

    id_subcategoria = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    categoria_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "categoria.id_categoria",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    nombre_subcategoria = Column(
        String(100),
        nullable=False,
    )

    es_activa_subcategoria = Column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
