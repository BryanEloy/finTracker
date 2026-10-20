from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.modules.grupos import service
from app.modules.grupos.schemas import GrupoListaSalida, GrupoSalida
from app.modules.usuarios.model import Usuario

router = APIRouter(tags=["Grupos"])


@router.get("/grupos", response_model=GrupoListaSalida)
def listar_grupos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    grupos = service.listar_grupos(db=db, usuario_id=usuario.id_usuario)
    return {"grupos": grupos, "total": len(grupos)}


@router.get("/grupos/{id_grupo}", response_model=GrupoSalida)
def obtener_grupo(
    id_grupo: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.obtener_grupo(db=db, usuario_id=usuario.id_usuario, id_grupo=id_grupo)
    except service.GrupoNoEncontradoError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GRUPO_NO_ENCONTRADO",
        )
