from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class EstadoFiltro(str, Enum):
    ACTIVA = "ACTIVA"
    INACTIVA = "INACTIVA"
    TODAS = "TODAS"


# =========================
# CATEGORÍA
# =========================

class CategoriaCrearEntrada(BaseModel):
    nombre_categoria: str = Field(
        min_length=2,
        max_length=100,
    )


class CategoriaActualizarEntrada(BaseModel):
    nombre_categoria: str = Field(
        min_length=2,
        max_length=100,
    )


class CategoriaEstadoEntrada(BaseModel):
    es_activa_categoria: StrictBool


class CategoriaSalida(BaseModel):
    id_categoria: UUID
    nombre_categoria: str
    es_activa_categoria: bool

    model_config = ConfigDict(from_attributes=True)


class CategoriaListaSalida(BaseModel):
    categorias: list[CategoriaSalida]
    total: int


class CategoriaEstadoSalida(BaseModel):
    id_categoria: UUID
    es_activa_categoria: bool


# =========================
# SUBCATEGORÍA
# =========================

class SubcategoriaCrearEntrada(BaseModel):
    nombre_subcategoria: str = Field(
        min_length=2,
        max_length=100,
    )


class SubcategoriaActualizarEntrada(BaseModel):
    nombre_subcategoria: str = Field(
        min_length=2,
        max_length=100,
    )


class SubcategoriaEstadoEntrada(BaseModel):
    es_activa_subcategoria: StrictBool


class SubcategoriaSalida(BaseModel):
    id_subcategoria: UUID
    categoria_id: UUID
    nombre_subcategoria: str
    es_activa_subcategoria: bool

    model_config = ConfigDict(from_attributes=True)


class SubcategoriaListaSalida(BaseModel):
    subcategorias: list[SubcategoriaSalida]
    total: int


class SubcategoriaEstadoSalida(BaseModel):
    id_subcategoria: UUID
    es_activa_subcategoria: bool