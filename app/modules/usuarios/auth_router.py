from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.usuarios.schemas import (
    TokenSalida,
    UsuarioPublico,
    UsuarioRegistroEntrada,
)
from app.modules.usuarios.service import (
    CorreoYaRegistradoError,
    CredencialesIncorrectasError,
    UsuarioDesactivadoError,
    autenticar_usuario,
    registrar_usuario,
)


router = APIRouter(
    prefix="/auth",
    tags=["Autenticación"],
)


# =========================================================
# REGISTRO
# POST /api/v1/auth/register
# =========================================================

@router.post(
    "/register",
    response_model=UsuarioPublico,
    status_code=status.HTTP_201_CREATED,
)
def register(
    datos: UsuarioRegistroEntrada,
    db: Session = Depends(get_db),
):
    try:
        usuario = registrar_usuario(
            db,
            datos,
        )

        return usuario

    except CorreoYaRegistradoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo ya está registrado",
        )


# =========================================================
# LOGIN
# POST /api/v1/auth/login
# =========================================================

@router.post(
    "/login",
    response_model=TokenSalida,
    status_code=status.HTTP_200_OK,
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    try:
        return autenticar_usuario(
            db,
            correo_usuario=form_data.username,
            password=form_data.password,
        )

    except CredencialesIncorrectasError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    except UsuarioDesactivadoError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado",
        )