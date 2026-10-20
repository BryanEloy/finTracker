from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.transacciones.model import TipoTransaccion


class TransaccionCrearEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_transaccion: TipoTransaccion
    cuenta_id: UUID
    cuenta_destino_id: UUID | None = None
    categoria_id: UUID | None = None
    subcategoria_id: UUID | None = None
    monto_transaccion: Decimal = Field(ge=Decimal("0.01"), le=Decimal("9999999999.99"), max_digits=12, decimal_places=2)
    monto_reduccion_deuda: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=12, decimal_places=2)
    fecha_operacion_transaccion: date | None = None
    comentario_transaccion: str | None = Field(default=None, max_length=500)
    referencia_transaccion: str | None = None

    @field_validator("monto_transaccion", "monto_reduccion_deuda", mode="before")
    @classmethod
    def decimal_como_texto(cls, valor):
        if valor is not None and not isinstance(valor, str):
            raise ValueError("Los importes deben enviarse como texto decimal")
        return valor

    @field_validator("comentario_transaccion", "referencia_transaccion")
    @classmethod
    def limpiar_texto(cls, valor: str | None):
        if valor is None:
            return None
        return valor.strip() or None

    @model_validator(mode="after")
    def validar_estructura(self):
        t = self.tipo_transaccion
        clasificados = {TipoTransaccion.GASTO, TipoTransaccion.DEVOLUCION_GASTO, TipoTransaccion.INGRESO_RESERVADO}
        entradas = {TipoTransaccion.INGRESO, TipoTransaccion.ANTICIPO_REEMBOLSABLE, TipoTransaccion.REEMBOLSO}
        con_destino = {TipoTransaccion.TRANSFERENCIA, TipoTransaccion.PRESTAMO_RECIBIDO, TipoTransaccion.PAGO_DEUDA}

        if t in clasificados:
            if self.categoria_id is None or self.cuenta_destino_id is not None:
                raise ValueError("Esta operación requiere categoría y no admite cuenta destino")
        elif t in entradas:
            if self.categoria_id is not None or self.subcategoria_id is not None or self.cuenta_destino_id is not None:
                raise ValueError("Esta operación no admite categoría, subcategoría ni cuenta destino")
        elif t in con_destino:
            if self.cuenta_destino_id is None or self.cuenta_destino_id == self.cuenta_id:
                raise ValueError("Se requiere una cuenta destino distinta del origen")
            if self.categoria_id is not None or self.subcategoria_id is not None:
                raise ValueError("Esta operación no admite categoría ni subcategoría")

        if t not in clasificados and self.subcategoria_id is not None:
            raise ValueError("La subcategoría solo se permite en operaciones clasificadas")
        if t != TipoTransaccion.PAGO_DEUDA and self.monto_reduccion_deuda is not None:
            raise ValueError("monto_reduccion_deuda solo se permite en PAGO_DEUDA")
        if self.monto_reduccion_deuda is not None and self.monto_reduccion_deuda > self.monto_transaccion:
            raise ValueError("La reducción de deuda no puede superar el monto")
        return self


class TransaccionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_transaccion: UUID
    cuenta_id: UUID
    tipo_transaccion: TipoTransaccion
    cuenta_destino_id: UUID | None
    categoria_id: UUID | None
    subcategoria_id: UUID | None
    monto_transaccion: Decimal
    monto_reduccion_deuda: Decimal | None
    fecha_registro_transaccion: datetime
    fecha_operacion_transaccion: date
    comentario_transaccion: str | None
    referencia_transaccion: str | None
    periodo_id: UUID | None
    grupo_id: UUID | None
    es_ingreso_reservado: bool


class TransaccionListaSalida(BaseModel):
    transacciones: list[TransaccionSalida]
    total: int
    limite: int
    offset: int
