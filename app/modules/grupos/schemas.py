from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GrupoSalida(BaseModel):
    id_grupo: UUID
    codigo_grupo: str
    nombre_grupo: str
    naturaleza_grupo: str
    porcentaje_sugerido_grupo: int
    es_activo_grupo: bool

    model_config = ConfigDict(from_attributes=True)


class GrupoListaSalida(BaseModel):
    grupos: list[GrupoSalida]
    total: int
