from datetime import datetime, date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UsuarioRegistroEntrada(BaseModel):
    nombre_usuario: str = Field(
        min_length=2,
        max_length=100,
    )

    correo_usuario: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )


class UsuarioPublico(BaseModel):
    id_usuario: UUID
    nombre_usuario: str
    correo_usuario: EmailStr

    ruta_foto_perfil_local_usuario: str | None = None

    notificaciones_presupuesto: bool
    notificaciones_periodicas: bool
    es_activo_usuario: bool

    fecha_registro_usuario: datetime
    fecha_desactivacion_usuario: datetime | None = None

    model_config = ConfigDict(
        from_attributes=True
    )


class UsuarioToken(BaseModel):
    id_usuario: UUID
    nombre_usuario: str
    correo_usuario: EmailStr
    ruta_foto_perfil_local_usuario: str | None = None
    es_activo_usuario: bool

    model_config = ConfigDict(
        from_attributes=True
    )



class UsuarioActualizarEntrada(BaseModel):
    nombre_usuario: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    ruta_foto_perfil_local_usuario: str | None = Field(
        default=None,
        max_length=255,
    )

    notificaciones_presupuesto: bool | None = None
    notificaciones_periodicas: bool | None = None

    @field_validator("nombre_usuario")
    @classmethod
    def validar_nombre(cls, valor: str | None) -> str:
        if valor is None:
            raise ValueError(
                "El nombre de usuario no puede ser null"
            )

        valor = valor.strip()

        if len(valor) < 2:
            raise ValueError(
                "El nombre debe tener al menos 2 caracteres"
            )

        return valor

    @field_validator("ruta_foto_perfil_local_usuario")
    @classmethod
    def validar_ruta_foto(
        cls,
        valor: str | None,
    ) -> str | None:
        if valor is None:
            return None

        valor = valor.strip().replace("\\", "/")

        if not valor:
            raise ValueError(
                "La ruta no puede estar vacía"
            )

        if (
            valor.startswith("/")
            or "://" in valor
            or ":" in valor
            or any(
                parte in (".", "..")
                for parte in valor.split("/")
            )
        ):
            raise ValueError(
                "La fotografía debe tener una ruta relativa válida"
            )

        return valor

class CambiarPasswordEntrada(BaseModel):
    password_actual: str

    password_nuevo: str = Field(
        min_length=8,
        max_length=128,
    )


class TokenSalida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioToken


from decimal import Decimal


class PeriodoActivoDashboard(BaseModel):
    id_periodo: UUID
    codigo_periodo: str
    tipo_periodo: str

    fecha_inicio_periodo: date
    fecha_fin_periodo: date

    estado_periodo: str
    periodo_vencido: bool

    monto_total_presupuesto: Decimal

    ingresos_libres_periodo: Decimal | None = None
    ingresos_reservados_periodo: Decimal | None = None
    ingresos_reales_periodo: Decimal | None = None

    base_repartible_periodo: Decimal | None = None
    gasto_conocido_total_periodo: Decimal | None = None
    aplicado_total_periodo: Decimal | None = None

    ingresos_nueva_deuda_periodo: Decimal | None = None

    monto_presupuesto_periodo: Decimal | None = None
    monto_restante_periodo: Decimal | None = None
    monto_excedido_periodo: Decimal | None = None

    porcentaje_consumido_periodo: Decimal | None = None
    estado_consumo_periodo: str | None = None

    pagos_deuda_periodo: Decimal | None = None

class ResumenDashboardSalida(BaseModel):
    id_usuario: UUID

    saldo_total_usuario: Decimal
    reserva_total_usuario: Decimal
    dinero_libre_total_usuario: Decimal

    limite_credito_total_usuario: Decimal
    credito_utilizado_total_usuario: Decimal
    credito_disponible_total_usuario: Decimal

    porcentaje_utilizacion_credito_usuario: Decimal | None
    periodo_activo: PeriodoActivoDashboard | None = None

