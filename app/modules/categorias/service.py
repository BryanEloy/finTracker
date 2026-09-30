from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.categorias.model import Categoria, Subcategoria
from app.modules.categorias import repository


# ============================================================
# EXCEPCIONES
# ============================================================

class CategoriaNoEncontradaError(Exception):
    pass


class NombreCategoriaDuplicadoError(Exception):
    pass


class CategoriaInactivaError(Exception):
    pass


class SubcategoriaNoEncontradaError(Exception):
    pass


class NombreSubcategoriaDuplicadoError(Exception):
    pass


class DatosInvalidosError(Exception):
    pass


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def normalizar_nombre(nombre: str) -> str:
    """
    Elimina únicamente espacios exteriores.

    No cambia mayúsculas/minúsculas.
    No elimina acentos.
    No compacta espacios interiores.
    """

    nombre_normalizado = nombre.strip()

    if not 2 <= len(nombre_normalizado) <= 100:
        raise DatosInvalidosError()

    return nombre_normalizado


# ============================================================
# CATEGORÍAS
# ============================================================

def crear_categoria(
    db: Session,
    usuario_id: UUID,
    nombre_categoria: str,
) -> Categoria:

    nombre = normalizar_nombre(nombre_categoria)

    existente = repository.obtener_categoria_por_nombre(
        db=db,
        usuario_id=usuario_id,
        nombre_categoria=nombre,
    )

    if existente:
        raise NombreCategoriaDuplicadoError()

    categoria = Categoria(
        usuario_id=usuario_id,
        nombre_categoria=nombre,
        es_activa_categoria=True,
    )

    try:
        return repository.crear_categoria(
            db=db,
            categoria=categoria,
        )

    except IntegrityError:
        # El índice UNIQUE de PostgreSQL también protege
        # contra dos solicitudes simultáneas.
        raise NombreCategoriaDuplicadoError()


def listar_categorias(
    db: Session,
    usuario_id: UUID,
    estado: str,
) -> list[Categoria]:

    return repository.listar_categorias(
        db=db,
        usuario_id=usuario_id,
        estado=estado,
    )


def obtener_categoria(
    db: Session,
    usuario_id: UUID,
    id_categoria: UUID,
) -> Categoria:

    categoria = repository.obtener_categoria_por_id(
        db=db,
        id_categoria=id_categoria,
        usuario_id=usuario_id,
    )

    if not categoria:
        raise CategoriaNoEncontradaError()

    return categoria


def renombrar_categoria(
    db: Session,
    usuario_id: UUID,
    id_categoria: UUID,
    nombre_categoria: str,
) -> Categoria:

    categoria = obtener_categoria(
        db=db,
        usuario_id=usuario_id,
        id_categoria=id_categoria,
    )

    nombre = normalizar_nombre(nombre_categoria)

    existente = repository.obtener_categoria_por_nombre(
        db=db,
        usuario_id=usuario_id,
        nombre_categoria=nombre,
    )

    if (
        existente
        and existente.id_categoria != categoria.id_categoria
    ):
        raise NombreCategoriaDuplicadoError()

    # Si después de normalizar es exactamente el mismo nombre,
    # no necesitamos hacer una actualización.
    if categoria.nombre_categoria == nombre:
        return categoria

    try:
        return repository.actualizar_nombre_categoria(
            db=db,
            categoria=categoria,
            nombre_categoria=nombre,
        )

    except IntegrityError:
        raise NombreCategoriaDuplicadoError()


def cambiar_estado_categoria(
    db: Session,
    usuario_id: UUID,
    id_categoria: UUID,
    nuevo_estado: bool,
) -> Categoria:

    categoria = obtener_categoria(
        db=db,
        usuario_id=usuario_id,
        id_categoria=id_categoria,
    )

    # Operación idempotente.
    if categoria.es_activa_categoria == nuevo_estado:
        return categoria

    return repository.cambiar_estado_categoria(
        db=db,
        categoria=categoria,
        nuevo_estado=nuevo_estado,
    )


# ============================================================
# SUBCATEGORÍAS
# ============================================================

def crear_subcategoria(
    db: Session,
    usuario_id: UUID,
    id_categoria: UUID,
    nombre_subcategoria: str,
) -> Subcategoria:

    # Además de comprobar existencia, comprueba propiedad.
    categoria = obtener_categoria(
        db=db,
        usuario_id=usuario_id,
        id_categoria=id_categoria,
    )

    if not categoria.es_activa_categoria:
        raise CategoriaInactivaError()

    nombre = normalizar_nombre(nombre_subcategoria)

    existente = repository.obtener_subcategoria_por_nombre(
        db=db,
        categoria_id=id_categoria,
        nombre_subcategoria=nombre,
    )

    if existente:
        raise NombreSubcategoriaDuplicadoError()

    subcategoria = Subcategoria(
        categoria_id=id_categoria,
        nombre_subcategoria=nombre,
        es_activa_subcategoria=True,
    )

    try:
        return repository.crear_subcategoria(
            db=db,
            subcategoria=subcategoria,
        )

    except IntegrityError:
        raise NombreSubcategoriaDuplicadoError()


def listar_subcategorias(
    db: Session,
    usuario_id: UUID,
    id_categoria: UUID,
    estado: str,
) -> list[Subcategoria]:

    # Es necesario comprobar que la categoría sea propia,
    # pero NO que esté activa.
    obtener_categoria(
        db=db,
        usuario_id=usuario_id,
        id_categoria=id_categoria,
    )

    return repository.listar_subcategorias(
        db=db,
        categoria_id=id_categoria,
        estado=estado,
    )


def obtener_subcategoria(
    db: Session,
    usuario_id: UUID,
    id_subcategoria: UUID,
) -> Subcategoria:

    subcategoria = repository.obtener_subcategoria_por_id(
        db=db,
        id_subcategoria=id_subcategoria,
        usuario_id=usuario_id,
    )

    if not subcategoria:
        raise SubcategoriaNoEncontradaError()

    return subcategoria


def renombrar_subcategoria(
    db: Session,
    usuario_id: UUID,
    id_subcategoria: UUID,
    nombre_subcategoria: str,
) -> Subcategoria:

    subcategoria = obtener_subcategoria(
        db=db,
        usuario_id=usuario_id,
        id_subcategoria=id_subcategoria,
    )

    nombre = normalizar_nombre(nombre_subcategoria)

    existente = repository.obtener_subcategoria_por_nombre(
        db=db,
        categoria_id=subcategoria.categoria_id,
        nombre_subcategoria=nombre,
    )

    if (
        existente
        and existente.id_subcategoria
        != subcategoria.id_subcategoria
    ):
        raise NombreSubcategoriaDuplicadoError()

    if subcategoria.nombre_subcategoria == nombre:
        return subcategoria

    try:
        return repository.actualizar_nombre_subcategoria(
            db=db,
            subcategoria=subcategoria,
            nombre_subcategoria=nombre,
        )

    except IntegrityError:
        raise NombreSubcategoriaDuplicadoError()


def cambiar_estado_subcategoria(
    db: Session,
    usuario_id: UUID,
    id_subcategoria: UUID,
    nuevo_estado: bool,
) -> Subcategoria:

    subcategoria = obtener_subcategoria(
        db=db,
        usuario_id=usuario_id,
        id_subcategoria=id_subcategoria,
    )

    # SUB-13:
    # repetir el estado actual siempre devuelve 200.
    if subcategoria.es_activa_subcategoria == nuevo_estado:
        return subcategoria

    # Solo necesitamos comprobar la categoría cuando
    # estamos haciendo INACTIVA -> ACTIVA.
    if nuevo_estado:
        categoria = repository.obtener_categoria_por_id(
            db=db,
            id_categoria=subcategoria.categoria_id,
            usuario_id=usuario_id,
        )

        # En condiciones normales nunca debería ser None,
        # porque obtener_subcategoria ya verificó propiedad.
        if not categoria:
            raise SubcategoriaNoEncontradaError()

        if not categoria.es_activa_categoria:
            raise CategoriaInactivaError()

    # ACTIVA -> INACTIVA sí está permitido aunque
    # la categoría padre esté inactiva.
    return repository.cambiar_estado_subcategoria(
        db=db,
        subcategoria=subcategoria,
        nuevo_estado=nuevo_estado,
    )