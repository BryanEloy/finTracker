from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class GrupoDistribucionEntrada(BaseModel):
    grupo_id: UUID
    porcentaje_asignado_grupo: int = Field(ge=0, le=100)
    porcentaje_alerta_grupo: int = Field(default=80, ge=1, le=100)

class PresupuestoCrearEntrada(BaseModel):
    codigo_periodo: str = Field(min_length=1, max_length=50)
    tipo_periodo: Literal["QUINCENAL", "SEMANAL", "MENSUAL", "PERSONALIZADO"]
    fecha_inicio_periodo: date
    fecha_fin_periodo: date
    monto_total_presupuesto: Decimal
    periodo_anterior_id: UUID | None = None
    grupos: list[GrupoDistribucionEntrada] = Field(min_length=4, max_length=4)

    @field_validator("monto_total_presupuesto", mode="before")
    @classmethod
    def validar_monto(cls, valor):
        if not isinstance(valor, str):
            raise ValueError("El monto debe enviarse como texto decimal")
        try:
            numero = Decimal(valor)
        except InvalidOperation as exc:
            raise ValueError("Monto decimal inválido") from exc
        if not numero.is_finite() or numero < 0 or numero > Decimal("9999999999.99") or numero.as_tuple().exponent < -2:
            raise ValueError("Monto fuera de rango o con más de dos decimales")
        return numero

    @model_validator(mode="after")
    def validar(self):
        if not self.codigo_periodo.strip():
            raise ValueError("El código no puede estar vacío")
        if self.fecha_fin_periodo < self.fecha_inicio_periodo:
            raise ValueError("La fecha final debe ser posterior o igual a la inicial")
        if len({g.grupo_id for g in self.grupos}) != 4:
            raise ValueError("Deben indicarse cuatro grupos distintos")
        if sum(g.porcentaje_asignado_grupo for g in self.grupos) != 100:
            raise ValueError("Los porcentajes deben sumar exactamente 100")
        return self

class PresupuestoActualizarEntrada(BaseModel):
    fecha_fin_periodo: date | None = None
    monto_total_presupuesto: Decimal | None = None
    @field_validator("monto_total_presupuesto", mode="before")
    @classmethod
    def validar_monto(cls, valor):
        if valor is None: return None
        return PresupuestoCrearEntrada.validar_monto(valor)
    @model_validator(mode="after")
    def no_vacio(self):
        if self.fecha_fin_periodo is None and self.monto_total_presupuesto is None:
            raise ValueError("Proporcione al menos un campo")
        return self

class PorcentajeGrupoActualizarEntrada(BaseModel):
    porcentaje_asignado_grupo: int = Field(ge=0, le=100)

class PresupuestoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_periodo: UUID
    usuario_id: UUID
    codigo_periodo: str
    tipo_periodo: str
    periodo_anterior_id: UUID | None
    fecha_inicio_periodo: date
    fecha_fin_periodo: date
    fecha_creacion_periodo: datetime
    fecha_cierre_periodo: datetime | None
    estado_periodo: str
    monto_total_presupuesto: Decimal
