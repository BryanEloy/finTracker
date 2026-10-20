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
    ResumenDashboardSalida,
    PeriodoActivoDashboard
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

def normalizar_correo(
    correo: str,
) -> str:

    return correo.strip().lower()


# =========================================================
# REGISTRO
# =========================================================

def registrar_usuario(
    db: Session,
    datos: UsuarioRegistroEntrada,
) -> Usuario:

    correo = normalizar_correo(
        str(datos.correo_usuario)
    )

    usuario_existente = (
        repository.obtener_por_correo(
            db,
            correo,
        )
    )

    if usuario_existente is not None:
        raise CorreoYaRegistradoError()

    password_hash_usuario = hash_password(
        datos.password
    )

    usuario = repository.crear(
        db,
        nombre_usuario=datos.nombre_usuario.strip(),
        correo_usuario=correo,
        password_hash_usuario=password_hash_usuario,
    )

    return usuario


# =========================================================
# LOGIN
# =========================================================

def autenticar_usuario(
    db: Session,
    correo_usuario: str,
    password: str,
) -> TokenSalida:

    correo = normalizar_correo(
        correo_usuario
    )

    usuario = repository.obtener_por_correo(
        db,
        correo,
    )

    if usuario is None:
        raise CredencialesIncorrectasError()

    password_correcto = verify_password(
        password,
        usuario.password_hash_usuario,
    )

    if not password_correcto:
        raise CredencialesIncorrectasError()

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
        ),
    )


# =========================================================
# ACTUALIZAR PERFIL
# =========================================================

def actualizar_perfil(
    db: Session,
    usuario: Usuario,
    datos: UsuarioActualizarEntrada,
) -> Usuario:

    cambios = datos.model_dump(
        exclude_unset=True
    )

    if not cambios:
        return usuario

    return repository.actualizar(
        db,
        usuario,
        cambios,
    )


# =========================================================
# CAMBIAR CONTRASEÑA
# =========================================================

def cambiar_password(
    db: Session,
    usuario: Usuario,
    datos: CambiarPasswordEntrada,
) -> None:

    password_correcto = verify_password(
        datos.password_actual,
        usuario.password_hash_usuario,
    )

    if not password_correcto:
        raise PasswordActualIncorrectoError()

    nuevo_password_hash = hash_password(
        datos.password_nuevo
    )

    repository.actualizar_password(
        db,
        usuario,
        nuevo_password_hash,
    )


# =========================================================
# DESACTIVAR CUENTA
# =========================================================

def desactivar_usuario(
    db: Session,
    usuario: Usuario,
) -> None:

    repository.desactivar(
        db,
        usuario,
    )

def reactivar_usuario(
    db: Session,
    usuario: Usuario,
) -> Usuario:
    return repository.reactivar(
        db,
        usuario,
    )


def consultar_resumen_dashboard(
    db: Session,
    usuario: Usuario,
) -> ResumenDashboardSalida | None:

    datos_financieros = repository.obtener_resumen_dashboard(
        db,
        usuario.id_usuario,
    )

    if datos_financieros is None:
        return None

    datos_periodo = repository.obtener_periodo_activo_dashboard(
        db,
        usuario.id_usuario,
    )

    resumen = ResumenDashboardSalida.model_validate(
        {
            **datos_financieros,
            "periodo_activo": (
                PeriodoActivoDashboard.model_validate(
                    datos_periodo
                )
                if datos_periodo is not None
                else None
            ),
        }
    )

    return resumen

