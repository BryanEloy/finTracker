"""Modelos ORM de las tablas vigentes. Las FK compuestas se validan en Neon.

No declarar ForeignKeyConstraint aquí evita requerir que todos los modelos
relacionados estén importados en Base.metadata al hacer flush.
"""
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class Periodo(Base):
    __tablename__ = "periodo"
    id_periodo = Column(UUID(as_uuid=True), primary_key=True)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id_usuario"), nullable=False)
    codigo_periodo = Column(String(50), nullable=False)
    tipo_periodo = Column(String, nullable=False)  # ENUM en Neon; escrituras usan SQL con CAST
    periodo_anterior_id = Column(UUID(as_uuid=True))
    fecha_inicio_periodo = Column(Date, nullable=False)
    fecha_fin_periodo = Column(Date, nullable=False)
    fecha_creacion_periodo = Column(DateTime(timezone=True), nullable=False)
    fecha_cierre_periodo = Column(DateTime(timezone=True))
    estado_periodo = Column(String, nullable=False)  # ENUM en Neon
    monto_total_presupuesto = Column(Numeric, nullable=False)

class DetallePeriodoGrupo(Base):
    __tablename__ = "detalle_periodo_grupo"
    id_detalle_periodo_grupo = Column(UUID(as_uuid=True), primary_key=True)
    periodo_id = Column(UUID(as_uuid=True), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), nullable=False)
    grupo_id = Column(UUID(as_uuid=True), nullable=False)
    porcentaje_asignado_grupo = Column(Integer, nullable=False)
    porcentaje_alerta_grupo = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("periodo_id", "grupo_id", name="uq_detalle_periodo_grupo"),)
