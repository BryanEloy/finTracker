from enum import Enum

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID, ENUM as PGEnum

from app.db.base import Base


class TipoTransaccion(str, Enum):
    INGRESO = "INGRESO"
    GASTO = "GASTO"
    TRANSFERENCIA = "TRANSFERENCIA"
    INGRESO_RESERVADO = "INGRESO_RESERVADO"
    PAGO_DEUDA = "PAGO_DEUDA"
    PRESTAMO_RECIBIDO = "PRESTAMO_RECIBIDO"
    ANTICIPO_REEMBOLSABLE = "ANTICIPO_REEMBOLSABLE"
    REEMBOLSO = "REEMBOLSO"
    DEVOLUCION_GASTO = "DEVOLUCION_GASTO"


class Transaccion(Base):
    __tablename__ = "transaccion"

    id_transaccion = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id_usuario", onupdate="RESTRICT", ondelete="RESTRICT"), nullable=False)
    cuenta_id = Column(UUID(as_uuid=True), nullable=False)
    tipo_transaccion = Column(PGEnum(TipoTransaccion, name="tipo_transaccion_enum", create_type=False), nullable=False)
    cuenta_destino_id = Column(UUID(as_uuid=True), nullable=True)
    categoria_id = Column(UUID(as_uuid=True), nullable=True)
    subcategoria_id = Column(UUID(as_uuid=True), nullable=True)
    monto_transaccion = Column(Numeric(12, 2), nullable=False)
    fecha_registro_transaccion = Column(DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"))
    comentario_transaccion = Column(String(500), nullable=True)
    periodo_id = Column(UUID(as_uuid=True), nullable=True)
    grupo_id = Column(UUID(as_uuid=True), nullable=True)
    monto_reduccion_deuda = Column(Numeric(12, 2), nullable=True)
    es_ingreso_reservado = Column(Boolean, nullable=False, server_default=text("false"))
    # Sin default de Python: el trigger asigna la fecha local de Ciudad de México.
    fecha_operacion_transaccion = Column(Date, nullable=False)
    referencia_transaccion = Column(String, nullable=True)
