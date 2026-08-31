from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.usuarios import repository
from app.modules.usuarios.model import Usuario


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login"
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Usuario:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    try:
        payload = decode_access_token(token)

        subject = payload.get("sub")

        if subject is None:
            raise credentials_exception

        id_usuario = UUID(subject)

    except (
        jwt.InvalidTokenError,
        ValueError,
        TypeError,
    ):
        raise credentials_exception

    usuario = repository.obtener_por_id(
        db,
        id_usuario
    )

    if usuario is None:
        raise credentials_exception

    if not usuario.es_activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado",
        )

    return usuario