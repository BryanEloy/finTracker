from decimal import Decimal
from uuid import UUID
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.modules.transacciones.model import TipoTransaccion


# ============================================================
# ENTRADA
# ============================================================

class TransaccionCrearEntrada(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    tipo_transaccion: TipoTransaccion

    cuenta_id: UUID

    cuenta_destino_id: UUID | None = None

    categoria_id: UUID | None = None

    subcategoria_id: UUID | None = None

    monto_transaccion: Decimal

    comentario_transaccion: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator(
        "monto_transaccion",
        mode="before",
    )
    @classmethod
    def validar_monto_como_texto(cls, valor):
        # El contrato V1 exige decimal enviado como texto.
        if not isinstance(valor, str):
            raise ValueError(
                "monto_transaccion debe enviarse como texto decimal"
            )

        return valor

    @field_validator("monto_transaccion")
    @classmethod
    def validar_monto(cls, valor: Decimal):
        if not valor.is_finite():
            raise ValueError("Monto inválido")

        if valor < Decimal("0.01"):
            raise ValueError("Monto inválido")

        if valor > Decimal("9999999999.99"):
            raise ValueError("Monto inválido")

        # exponent < -2 significa más de dos decimales.
        if valor.as_tuple().exponent < -2:
            raise ValueError(
                "El monto admite máximo dos decimales"
            )

        return valor

    @field_validator(
        "comentario_transaccion",
        mode="before",
    )
    @classmethod
    def normalizar_comentario(cls, valor):
        if valor is None:
            return None

        if not isinstance(valor, str):
            raise ValueError("Comentario inválido")

        valor = valor.strip()

        if valor == "":
            return None

        if len(valor) > 500:
            raise ValueError("Comentario demasiado largo")

        return valor


# ============================================================
# SALIDA
# ============================================================

class TransaccionSalida(BaseModel):
    id_transaccion: UUID

    cuenta_id: UUID

    tipo_transaccion: TipoTransaccion

    cuenta_destino_id: UUID | None

    categoria_id: UUID | None

    subcategoria_id: UUID | None

    monto_transaccion: Decimal

    fecha_registro_transaccion: datetime

    comentario_transaccion: str | None

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================
# LISTADO
# ============================================================

class TransaccionListaSalida(BaseModel):
    transacciones: list[TransaccionSalida]

    total: int

    limite: int

    offset: int
