from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.modules.usuarios import repository
from app.modules.usuarios.model import Usuario
from app.modules.usuarios.schemas import (
    CambiarPasswordEntrada,
    TokenSalida,
    UsuarioActualizarEntrada,
    UsuarioRegistroEntrada,
    UsuarioToken,
)


# =========================================================
# EXCEPCIONES DEL MÓDULO
# =========================================================

class CorreoYaRegistradoError(Exception):
    pass


class CredencialesIncorrectasError(Exception):
    pass


class UsuarioDesactivadoError(Exception):
    pass


class PasswordActualIncorrectoError(Exception):
    pass


# =========================================================
# FUNCIONES AUXILIARES
# =========================================================

def normalizar_correo(correo: str) -> str:
    return correo.strip().lower()


# =========================================================
# REGISTRO
# =========================================================

def registrar_usuario(
    db: Session,
    datos: UsuarioRegistroEntrada
) -> Usuario:

    correo = normalizar_correo(
        str(datos.correo_usuario)
    )

    usuario_existente = repository.obtener_por_correo(
        db,
        correo
    )

    if usuario_existente is not None:
        raise CorreoYaRegistradoError()

    password_hash = hash_password(
        datos.password
    )

    usuario = repository.crear(
        db,
        nombre_usuario=datos.nombre_usuario.strip(),
        correo_usuario=correo,
        password_hash=password_hash,
    )

    return usuario


# =========================================================
# LOGIN
# =========================================================

def autenticar_usuario(
    db: Session,
    correo_usuario: str,
    password: str
) -> TokenSalida:

    correo = normalizar_correo(
        correo_usuario
    )

    usuario = repository.obtener_por_correo(
        db,
        correo
    )

    if usuario is None:
        raise CredencialesIncorrectasError()

    if not verify_password(
        password,
        usuario.password_hash
    ):
        raise CredencialesIncorrectasError()

    if not usuario.es_activo:
        raise UsuarioDesactivadoError()

    repository.actualizar_ultimo_acceso(
        db,
        usuario
    )

    access_token = create_access_token(
        usuario.id_usuario
    )

    return TokenSalida(
        access_token=access_token,
        token_type="bearer",
        expires_in=(
            settings.JWT_EXPIRE_MINUTES * 60
        ),
        usuario=UsuarioToken.model_validate(
            usuario
        )
    )


# =========================================================
# ACTUALIZAR PERFIL
# =========================================================

def actualizar_perfil(
    db: Session,
    usuario: Usuario,
    datos: UsuarioActualizarEntrada
) -> Usuario:

    return repository.actualizar(
        db,
        usuario,
        nombre_usuario=(
            datos.nombre_usuario.strip()
            if datos.nombre_usuario is not None
            else None
        ),
        avatar_codigo=datos.avatar_codigo,
        notificaciones_presupuesto=(
            datos.notificaciones_presupuesto
        ),
    )


# =========================================================
# CAMBIAR CONTRASEÑA
# =========================================================

def cambiar_password(
    db: Session,
    usuario: Usuario,
    datos: CambiarPasswordEntrada
) -> None:

    password_correcto = verify_password(
        datos.password_actual,
        usuario.password_hash
    )

    if not password_correcto:
        raise PasswordActualIncorrectoError()

    nuevo_password_hash = hash_password(
        datos.password_nuevo
    )

    repository.actualizar_password(
        db,
        usuario,
        nuevo_password_hash
    )


# =========================================================
# DESACTIVAR CUENTA
# =========================================================

def desactivar_usuario(
    db: Session,
    usuario: Usuario
) -> None:

    repository.desactivar(
        db,
        usuario
    )