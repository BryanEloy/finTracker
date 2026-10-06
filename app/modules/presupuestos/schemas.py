from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.modules.presupuestos.model import EstadoPresupuesto

from app.modules.transacciones.schemas import TransaccionSalida


# =========================================================
# Funciones auxiliares de validación
# =========================================================

def validar_decimal_entrada(valor) -> Decimal:
    """
    Valida montos monetarios recibidos desde el cliente.

    Reglas:
    - Debe llegar como string.
    - Debe tener máximo 2 decimales.
    - No se redondea.
    - Debe estar entre 0.01 y 9999999999.99.
    """

    if not isinstance(valor, str):
        raise ValueError("El monto debe enviarse como texto decimal")

    if not valor:
        raise ValueError("Monto inválido")

    partes = valor.split(".")

    if len(partes) > 2:
        raise ValueError("Monto inválido")

    if not partes[0].isdigit():
        raise ValueError("Monto inválido")

    if len(partes) == 2:
        if (
            not partes[1].isdigit()
            or len(partes[1]) == 0
            or len(partes[1]) > 2
        ):
            raise ValueError("Monto inválido")

    decimal = Decimal(valor)

    if not decimal.is_finite():
        raise ValueError("Monto inválido")

    if decimal < Decimal("0.01"):
        raise ValueError("Monto inválido")

    if decimal > Decimal("9999999999.99"):
        raise ValueError("Monto inválido")

    return decimal


# =========================================================
# ENTRADA - CREACIÓN
# =========================================================

class DetallePresupuestoCrearEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: UUID

    porcentaje_asignado_presupuesto: int = Field(
        ge=1,
        le=100,
        strict=True,
    )

    porcentaje_alerta_presupuesto: int = Field(
        default=80,
        ge=1,
        le=100,
        strict=True,
    )


class PresupuestoCrearEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_fin_presupuesto: date

    monto_limite_presupuesto: Decimal

    detalles: list[DetallePresupuestoCrearEntrada] = Field(
        min_length=1,
        max_length=100,
    )

    @field_validator(
        "monto_limite_presupuesto",
        mode="before",
    )
    @classmethod
    def validar_monto_limite(cls, valor):
        return validar_decimal_entrada(valor)

    @model_validator(mode="after")
    def validar_distribucion(self):
        categorias = [
            detalle.categoria_id
            for detalle in self.detalles
        ]

        if len(categorias) != len(set(categorias)):
            raise ValueError("Categorías repetidas")

        suma_porcentajes = sum(
            detalle.porcentaje_asignado_presupuesto
            for detalle in self.detalles
        )

        if suma_porcentajes != 100:
            raise ValueError(
                "La distribución debe sumar exactamente 100"
            )

        return self


# =========================================================
# ENTRADA - CIERRE
# =========================================================

class AccionCierrePresupuesto(str, Enum):
    FINALIZAR = "FINALIZAR"
    CANCELAR = "CANCELAR"


class PresupuestoCierreEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accion: AccionCierrePresupuesto


# =========================================================
# SALIDAS - DETALLE DE DISTRIBUCIÓN
# =========================================================

class DetallePresupuestoSalida(BaseModel):
    id_detalle_presupuesto: UUID
    categoria_id: UUID

    nombre_categoria: str

    porcentaje_asignado_presupuesto: int
    porcentaje_alerta_presupuesto: int

    monto_limite_categoria: Decimal
    monto_consumido_categoria: Decimal
    monto_restante_categoria: Decimal
    monto_excedido_categoria: Decimal

    porcentaje_consumido_categoria: Decimal

    indicador_categoria: str


# =========================================================
# SALIDA - RESUMEN DEL PRESUPUESTO
# =========================================================

class PresupuestoResumen(BaseModel):
    id_presupuesto: UUID

    fecha_inicio_presupuesto: datetime
    fecha_fin_presupuesto: date
    fecha_cierre_presupuesto: datetime | None

    estado_presupuesto: EstadoPresupuesto

    monto_limite_presupuesto: Decimal

    monto_consumido_presupuesto: Decimal
    monto_restante_presupuesto: Decimal
    monto_excedido_presupuesto: Decimal

    porcentaje_consumido_presupuesto: Decimal

    indicador_presupuesto: str

    periodo_vencido: bool


# =========================================================
# SALIDA - DETALLE COMPLETO
# =========================================================

class PresupuestoDetalle(BaseModel):
    presupuesto: PresupuestoResumen

    monto_consumido_presupuestado: Decimal
    monto_consumido_no_presupuestado: Decimal

    detalles: list[DetallePresupuestoSalida]


# =========================================================
# SALIDA - LISTADO
# =========================================================

class PresupuestoListaSalida(BaseModel):
    presupuestos: list[PresupuestoResumen]

    total: int
    limite: int
    offset: int

# =========================================================
# SALIDA - GASTOS DEL PRESUPUESTO
# =========================================================

class PresupuestoGastosSalida(BaseModel):
    gastos: list[TransaccionSalida]

    total: int
    limite: int
    offset: int