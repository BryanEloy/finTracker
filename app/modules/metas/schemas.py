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

from app.modules.metas.model import (
    EstadoMeta,
    TipoAsignacion,
)


# ============================================================
# AUXILIARES
# ============================================================

def validar_decimal_entrada(valor) -> Decimal:
    """
    El contrato exige que los montos lleguen como texto decimal.
    No aceptamos números JSON.
    """

    if not isinstance(valor, str):
        raise ValueError(
            "El monto debe enviarse como texto decimal"
        )

    # Evita notación científica, signos y formatos ambiguos.
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


def normalizar_texto_opcional(
    valor,
    maximo: int,
):
    if valor is None:
        return None

    if not isinstance(valor, str):
        raise ValueError("Texto inválido")

    valor = valor.strip()

    if valor == "":
        return None

    if len(valor) > maximo:
        raise ValueError("Texto demasiado largo")

    return valor


# ============================================================
# CREAR META
# ============================================================

class MetaCrearEntrada(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    cuenta_id: UUID

    nombre_meta: str

    monto_objetivo_meta: Decimal

    fecha_limite_meta: date

    descripcion_meta: str | None = None

    @field_validator("nombre_meta")
    @classmethod
    def validar_nombre(cls, valor: str):
        valor = valor.strip()

        if len(valor) < 2 or len(valor) > 100:
            raise ValueError("Nombre inválido")

        return valor

    @field_validator(
        "monto_objetivo_meta",
        mode="before",
    )
    @classmethod
    def validar_objetivo(cls, valor):
        return validar_decimal_entrada(valor)

    @field_validator(
        "descripcion_meta",
        mode="before",
    )
    @classmethod
    def validar_descripcion(cls, valor):
        return normalizar_texto_opcional(
            valor,
            500,
        )


# ============================================================
# ACTUALIZAR META
# ============================================================

class MetaActualizarEntrada(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    nombre_meta: str | None = None
    descripcion_meta: str | None = None

    @model_validator(mode="before")
    @classmethod
    def validar_body(cls, datos):
        if not isinstance(datos, dict):
            raise ValueError("Body inválido")

        if len(datos) == 0:
            raise ValueError(
                "Debe enviarse al menos un campo"
            )

        if (
            "nombre_meta" in datos
            and datos["nombre_meta"] is None
        ):
            raise ValueError(
                "nombre_meta no puede ser NULL"
            )

        return datos

    @field_validator("nombre_meta")
    @classmethod
    def validar_nombre(cls, valor):
        if valor is None:
            return valor

        valor = valor.strip()

        if len(valor) < 2 or len(valor) > 100:
            raise ValueError("Nombre inválido")

        return valor

    @field_validator(
        "descripcion_meta",
        mode="before",
    )
    @classmethod
    def validar_descripcion(cls, valor):
        return normalizar_texto_opcional(
            valor,
            500,
        )


# ============================================================
# CIERRE
# ============================================================

class AccionCierre(str, Enum):
    FINALIZAR = "FINALIZAR"
    CANCELAR = "CANCELAR"


class MetaCierreEntrada(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    accion: AccionCierre


# ============================================================
# RESPUESTA COMÚN DE META
# ============================================================

class MetaSalida(BaseModel):
    id_meta: UUID
    cuenta_id: UUID

    nombre_meta: str
    descripcion_meta: str | None

    monto_objetivo_meta: Decimal

    fecha_limite_meta: date
    fecha_creacion_meta: datetime
    fecha_cierre_meta: datetime | None

    estado_meta: EstadoMeta

    # Valores calculados
    monto_actual_meta: Decimal
    monto_faltante_meta: Decimal
    porcentaje_avance_meta: Decimal
    reserva_vigente_meta: Decimal
    plazo_vencido: bool


# ============================================================
# LISTADO
# ============================================================

class MetaListaSalida(BaseModel):
    metas: list[MetaSalida]

    total: int
    limite: int
    offset: int


# ============================================================
# RESUMEN DE CUENTA
# ============================================================

class ResumenCuentaMeta(BaseModel):
    saldo_actual_cuenta: Decimal
    reserva_total_cuenta: Decimal
    dinero_libre_cuenta: Decimal
    disponible_para_aportar: Decimal
    deficit_reservas_cuenta: Decimal


class MetaDetalleSalida(BaseModel):
    meta: MetaSalida
    resumen_cuenta: ResumenCuentaMeta


# ============================================================
# CREAR ASIGNACIÓN
# ============================================================

class AsignacionCrearEntrada(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    tipo_asignacion: TipoAsignacion

    monto_asignacion: Decimal

    comentario_asignacion: str | None = None

    @field_validator(
        "monto_asignacion",
        mode="before",
    )
    @classmethod
    def validar_monto(cls, valor):
        return validar_decimal_entrada(valor)

    @field_validator(
        "comentario_asignacion",
        mode="before",
    )
    @classmethod
    def validar_comentario(cls, valor):
        return normalizar_texto_opcional(
            valor,
            500,
        )


# ============================================================
# RESPUESTA ASIGNACIÓN
# ============================================================

class AsignacionSalida(BaseModel):
    id_asignacion: UUID
    meta_id: UUID

    tipo_asignacion: TipoAsignacion
    monto_asignacion: Decimal

    fecha_registro_asignacion: datetime
    comentario_asignacion: str | None

    model_config = ConfigDict(
        from_attributes=True,
    )


class AsignacionListaSalida(BaseModel):
    asignaciones: list[AsignacionSalida]

    total: int
    limite: int
    offset: int