from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.grupos import repository


class GrupoNoEncontradoError(Exception):
    pass


def listar_grupos(db: Session, usuario_id: UUID) -> list[dict]:
    return repository.listar_grupos(db=db, usuario_id=usuario_id)


def obtener_grupo(db: Session, usuario_id: UUID, id_grupo: UUID) -> dict:
    grupo = repository.obtener_grupo_por_id(db=db, usuario_id=usuario_id, id_grupo=id_grupo)
    if grupo is None:
        raise GrupoNoEncontradoError()
    return grupo
