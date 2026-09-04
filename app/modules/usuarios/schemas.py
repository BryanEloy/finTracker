from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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