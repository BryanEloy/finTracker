from sqlalchemy import Boolean, Column, ForeignKey, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Grupo(Base):
    __tablename__ = "grupo"

    id_grupo = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id_usuario", onupdate="RESTRICT", ondelete="RESTRICT"), nullable=False)
    codigo_grupo = Column(String, nullable=False)
    nombre_grupo = Column(String, nullable=False)
    # Se mantiene como texto para lectura; PostgreSQL lo almacena como enum.
    # No se crean tablas ni se modifican enums mediante este módulo.
    naturaleza_grupo = Column(String, nullable=False)
    porcentaje_sugerido_grupo = Column(SmallInteger, nullable=False, server_default=text("0"))
    es_activo_grupo = Column(Boolean, nullable=False, server_default=text("true"))
