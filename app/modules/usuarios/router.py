from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_user,
    get_authenticated_user
)
from app.db.session import get_db
from app.modules.usuarios.model import Usuario
from app.modules.usuarios.schemas import (
    CambiarPasswordEntrada,
    UsuarioActualizarEntrada,
    UsuarioPublico,
    ResumenDashboardSalida
)
from app.modules.usuarios.service import (
    PasswordActualIncorrectoError,
    actualizar_perfil,
    cambiar_password,
    desactivar_usuario,
    reactivar_usuario,
    consultar_resumen_dashboard
)


router = APIRouter(
    prefix="/usuarios",
    tags=["Usuarios"],
)


# =========================================================
# OBTENER MI PERFIL
# GET /api/v1/usuarios/me
# =========================================================

@router.get(
    "/me",
    response_model=UsuarioPublico,
    status_code=status.HTTP_200_OK,
)
def obtener_mi_perfil(
    usuario: Usuario = Depends(get_current_user),
):
    return usuario


# =========================================================
# ACTUALIZAR MI PERFIL
# PATCH /api/v1/usuarios/me
# =========================================================

@router.patch(
    "/me",
    response_model=UsuarioPublico,
    status_code=status.HTTP_200_OK,
)
def actualizar_mi_perfil(
    datos: UsuarioActualizarEntrada,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return actualizar_perfil(
        db,
        usuario,
        datos,
    )


# =========================================================
# CAMBIAR MI CONTRASEÑA
# PUT /api/v1/usuarios/me/password
# =========================================================

@router.put(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cambiar_mi_password(
    datos: CambiarPasswordEntrada,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        cambiar_password(
            db,
            usuario,
            datos,
        )

    except PasswordActualIncorrectoError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta",
        )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


# =========================================================
# DESACTIVAR MI CUENTA
# DELETE /api/v1/usuarios/me
# =========================================================

@router.patch(
    "/me/estado",
    status_code=status.HTTP_204_NO_CONTENT,
)
def desactivar_mi_cuenta(
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    desactivar_usuario(
        db,
        usuario,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


# =========================================================
# REACTIVAR MI CUENTA
# PATCH /api/v1/usuarios/me/reactivar
# =========================================================

@router.patch(
    "/me/reactivar",
    response_model=UsuarioPublico,
    status_code=status.HTTP_200_OK,
)
def reactivar_mi_cuenta(
    usuario: Usuario = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    return reactivar_usuario(
        db,
        usuario,
    )

# =========================================================
# RESUMEN FINANCIERO DEL DASHBOARD
# GET /api/v1/usuarios/me/resumen-dashboard
# =========================================================

@router.get(
    "/me/resumen-dashboard",
    response_model=ResumenDashboardSalida,
    status_code=status.HTTP_200_OK,
)
def obtener_resumen_dashboard(
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resumen = consultar_resumen_dashboard(
        db,
        usuario,
    )

    if resumen is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el resumen financiero del usuario",
        )

    return resumen
