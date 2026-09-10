from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.cuentas.model import TipoCuenta


class EstadoCuenta(str, Enum):
    ACTIVA = "ACTIVA"
    INACTIVA = "INACTIVA"
    TODAS = "TODAS"


class OperacionCuenta(str, Enum):
    INGRESO = "INGRESO"
    GASTO = "GASTO"
    TRANSFERENCIA_ORIGEN = "TRANSFERENCIA_ORIGEN"
    TRANSFERENCIA_DESTINO = "TRANSFERENCIA_DESTINO"


class CuentaCrearEntrada(BaseModel):
    nombre_cuenta: str = Field(
        min_length=2,
        max_length=100,
    )

    tipo_cuenta: TipoCuenta

    institucion_cuenta: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    numero_cuenta: str | None = Field(
        default=None,
        max_length=50,
    )

    saldo_inicial_cuenta: Decimal = Field(
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
    )

    limite_credito_cuenta: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=12,
        decimal_places=2,
    )


class CuentaActualizarEntrada(BaseModel):
    nombre_cuenta: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    institucion_cuenta: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    numero_cuenta: str | None = Field(
        default=None,
        max_length=50,
    )

    saldo_inicial_cuenta: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
    )

    limite_credito_cuenta: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=12,
        decimal_places=2,
    )


class CuentaEstadoEntrada(BaseModel):
    es_activa_cuenta: bool


class CuentaPublica(BaseModel):
    id_cuenta: UUID
    nombre_cuenta: str
    tipo_cuenta: TipoCuenta
    institucion_cuenta: str | None
    numero_cuenta_enmascarado: str | None

    es_activa_cuenta: bool
    fecha_creacion_cuenta: datetime

    saldo_inicial_cuenta: Decimal
    saldo_actual_cuenta: Decimal

    limite_credito_cuenta: Decimal | None

    credito_utilizado_cuenta: Decimal | None
    saldo_disponible_credito_cuenta: Decimal | None
    porcentaje_utilizacion_credito_cuenta: Decimal | None


class CuentaListaItem(BaseModel):
    id_cuenta: UUID
    nombre_cuenta: str
    tipo_cuenta: TipoCuenta
    institucion_cuenta: str | None
    numero_cuenta_enmascarado: str | None
    es_activa_cuenta: bool
    saldo_actual_cuenta: Decimal


class CuentaListaSalida(BaseModel):
    cuentas: list[CuentaListaItem]
    total: int


class CuentaEstadoSalida(BaseModel):
    id_cuenta: UUID
    es_activa_cuenta: bool


class CuentaORM(BaseModel):
    id_cuenta: UUID
    usuario_id: UUID
    nombre_cuenta: str
    tipo_cuenta: TipoCuenta
    institucion_cuenta: str | None
    numero_cuenta: str | None
    es_activa_cuenta: bool
    fecha_creacion_cuenta: datetime
    saldo_inicial_cuenta: Decimal
    limite_credito_cuenta: Decimal | None

    model_config = ConfigDict(from_attributes=True)