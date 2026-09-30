from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.modules.categorias import service
from app.modules.categorias.schemas import (
    CategoriaActualizarEntrada,
    CategoriaCrearEntrada,
    CategoriaEstadoEntrada,
    CategoriaEstadoSalida,
    CategoriaListaSalida,
    CategoriaSalida,
    EstadoFiltro,
    SubcategoriaActualizarEntrada,
    SubcategoriaCrearEntrada,
    SubcategoriaEstadoEntrada,
    SubcategoriaEstadoSalida,
    SubcategoriaListaSalida,
    SubcategoriaSalida,
)
from app.modules.usuarios.model import Usuario


router = APIRouter(tags=["Categorías"])


# ============================================================
# CATEGORÍAS
# ============================================================

@router.post(
    "/categorias",
    response_model=CategoriaSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_categoria(
    datos: CategoriaCrearEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.crear_categoria(
            db=db,
            usuario_id=usuario.id_usuario,
            nombre_categoria=datos.nombre_categoria,
        )

    except service.NombreCategoriaDuplicadoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="NOMBRE_CATEGORIA_DUPLICADO",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DATOS_INVALIDOS",
        )


@router.get(
    "/categorias",
    response_model=CategoriaListaSalida,
)
def listar_categorias(
    estado: EstadoFiltro = Query(default=EstadoFiltro.ACTIVA),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    categorias = service.listar_categorias(
        db=db,
        usuario_id=usuario.id_usuario,
        estado=estado.value,
    )

    return {
        "categorias": categorias,
        "total": len(categorias),
    }


@router.get(
    "/categorias/{id_categoria}",
    response_model=CategoriaSalida,
)
def obtener_categoria(
    id_categoria: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.obtener_categoria(
            db=db,
            usuario_id=usuario.id_usuario,
            id_categoria=id_categoria,
        )

    except service.CategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CATEGORIA_NO_ENCONTRADA",
        )


@router.patch(
    "/categorias/{id_categoria}",
    response_model=CategoriaSalida,
)
def renombrar_categoria(
    id_categoria: UUID,
    datos: CategoriaActualizarEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.renombrar_categoria(
            db=db,
            usuario_id=usuario.id_usuario,
            id_categoria=id_categoria,
            nombre_categoria=datos.nombre_categoria,
        )

    except service.CategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CATEGORIA_NO_ENCONTRADA",
        )

    except service.NombreCategoriaDuplicadoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="NOMBRE_CATEGORIA_DUPLICADO",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DATOS_INVALIDOS",
        )


@router.patch(
    "/categorias/{id_categoria}/estado",
    response_model=CategoriaEstadoSalida,
)
def cambiar_estado_categoria(
    id_categoria: UUID,
    datos: CategoriaEstadoEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        categoria = service.cambiar_estado_categoria(
            db=db,
            usuario_id=usuario.id_usuario,
            id_categoria=id_categoria,
            nuevo_estado=datos.es_activa_categoria,
        )

        return {
            "id_categoria": categoria.id_categoria,
            "es_activa_categoria": categoria.es_activa_categoria,
        }

    except service.CategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CATEGORIA_NO_ENCONTRADA",
        )


# ============================================================
# SUBCATEGORÍAS
# ============================================================

@router.post(
    "/categorias/{id_categoria}/subcategorias",
    response_model=SubcategoriaSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_subcategoria(
    id_categoria: UUID,
    datos: SubcategoriaCrearEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.crear_subcategoria(
            db=db,
            usuario_id=usuario.id_usuario,
            id_categoria=id_categoria,
            nombre_subcategoria=datos.nombre_subcategoria,
        )

    except service.CategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CATEGORIA_NO_ENCONTRADA",
        )

    except service.CategoriaInactivaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CATEGORIA_INACTIVA",
        )

    except service.NombreSubcategoriaDuplicadoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="NOMBRE_SUBCATEGORIA_DUPLICADO",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DATOS_INVALIDOS",
        )


@router.get(
    "/categorias/{id_categoria}/subcategorias",
    response_model=SubcategoriaListaSalida,
)
def listar_subcategorias(
    id_categoria: UUID,
    estado: EstadoFiltro = Query(default=EstadoFiltro.ACTIVA),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        subcategorias = service.listar_subcategorias(
            db=db,
            usuario_id=usuario.id_usuario,
            id_categoria=id_categoria,
            estado=estado.value,
        )

        return {
            "subcategorias": subcategorias,
            "total": len(subcategorias),
        }

    except service.CategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CATEGORIA_NO_ENCONTRADA",
        )


@router.get(
    "/subcategorias/{id_subcategoria}",
    response_model=SubcategoriaSalida,
)
def obtener_subcategoria(
    id_subcategoria: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.obtener_subcategoria(
            db=db,
            usuario_id=usuario.id_usuario,
            id_subcategoria=id_subcategoria,
        )

    except service.SubcategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SUBCATEGORIA_NO_ENCONTRADA",
        )


@router.patch(
    "/subcategorias/{id_subcategoria}",
    response_model=SubcategoriaSalida,
)
def renombrar_subcategoria(
    id_subcategoria: UUID,
    datos: SubcategoriaActualizarEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.renombrar_subcategoria(
            db=db,
            usuario_id=usuario.id_usuario,
            id_subcategoria=id_subcategoria,
            nombre_subcategoria=datos.nombre_subcategoria,
        )

    except service.SubcategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SUBCATEGORIA_NO_ENCONTRADA",
        )

    except service.NombreSubcategoriaDuplicadoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="NOMBRE_SUBCATEGORIA_DUPLICADO",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DATOS_INVALIDOS",
        )


@router.patch(
    "/subcategorias/{id_subcategoria}/estado",
    response_model=SubcategoriaEstadoSalida,
)
def cambiar_estado_subcategoria(
    id_subcategoria: UUID,
    datos: SubcategoriaEstadoEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        subcategoria = service.cambiar_estado_subcategoria(
            db=db,
            usuario_id=usuario.id_usuario,
            id_subcategoria=id_subcategoria,
            nuevo_estado=datos.es_activa_subcategoria,
        )

        return {
            "id_subcategoria": subcategoria.id_subcategoria,
            "es_activa_subcategoria":
                subcategoria.es_activa_subcategoria,
        }

    except service.SubcategoriaNoEncontradaError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SUBCATEGORIA_NO_ENCONTRADA",
        )

    except service.CategoriaInactivaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CATEGORIA_INACTIVA",
        )