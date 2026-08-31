from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# =========================================================
# REGISTRO
# POST /api/v1/auth/register
# =========================================================

class UsuarioRegistroEntrada(BaseModel):
    nombre_usuario: str = Field(
        min_length=2,
        max_length=100
    )

    correo_usuario: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128
    )


# =========================================================
# USUARIO PÚBLICO
# GET /api/v1/usuarios/me
# PATCH /api/v1/usuarios/me
# POST /api/v1/auth/register
# =========================================================

class UsuarioPublico(BaseModel):
    id_usuario: UUID
    nombre_usuario: str
    correo_usuario: EmailStr
    avatar_codigo: str
    notificaciones_presupuesto: bool
    es_activo: bool
    fecha_registro_usuario: datetime
    ultimo_acceso_usuario: datetime | None = None

    model_config = ConfigDict(
        from_attributes=True
    )


# =========================================================
# USUARIO RESUMIDO PARA LOGIN
# POST /api/v1/auth/login
# =========================================================

class UsuarioToken(BaseModel):
    id_usuario: UUID
    nombre_usuario: str
    correo_usuario: EmailStr
    avatar_codigo: str

    model_config = ConfigDict(
        from_attributes=True
    )


# =========================================================
# ACTUALIZAR PERFIL
# PATCH /api/v1/usuarios/me
# =========================================================

class UsuarioActualizarEntrada(BaseModel):
    nombre_usuario: str | None = Field(
        default=None,
        min_length=2,
        max_length=100
    )

    avatar_codigo: str | None = Field(
        default=None,
        max_length=50
    )

    notificaciones_presupuesto: bool | None = None


# =========================================================
# CAMBIAR CONTRASEÑA
# PUT /api/v1/usuarios/me/password
# =========================================================

class CambiarPasswordEntrada(BaseModel):
    password_actual: str

    password_nuevo: str = Field(
        min_length=8,
        max_length=128
    )


# =========================================================
# TOKEN
# POST /api/v1/auth/login
# =========================================================

class TokenSalida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioToken