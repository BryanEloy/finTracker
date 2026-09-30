from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.categorias.model import Categoria, Subcategoria


# ============================================================
# CATEGORÍAS
# ============================================================

def obtener_categoria_por_id(
    db: Session,
    id_categoria: UUID,
    usuario_id: UUID,
) -> Categoria | None:
    """
    Obtiene una categoría únicamente si pertenece al usuario.
    """

    stmt = select(Categoria).where(
        Categoria.id_categoria == id_categoria,
        Categoria.usuario_id == usuario_id,
    )

    return db.scalar(stmt)


def obtener_categoria_por_nombre(
    db: Session,
    usuario_id: UUID,
    nombre_categoria: str,
) -> Categoria | None:
    """
    Busca duplicados sin distinguir mayúsculas/minúsculas.
    Incluye categorías activas e inactivas.
    """

    stmt = select(Categoria).where(
        Categoria.usuario_id == usuario_id,
        func.lower(Categoria.nombre_categoria)
        == nombre_categoria.lower(),
    )

    return db.scalar(stmt)


def listar_categorias(
    db: Session,
    usuario_id: UUID,
    estado: str,
) -> list[Categoria]:

    stmt = select(Categoria).where(
        Categoria.usuario_id == usuario_id
    )

    if estado == "ACTIVA":
        stmt = stmt.where(
            Categoria.es_activa_categoria.is_(True)
        )

    elif estado == "INACTIVA":
        stmt = stmt.where(
            Categoria.es_activa_categoria.is_(False)
        )

    stmt = stmt.order_by(
        func.lower(Categoria.nombre_categoria),
        Categoria.id_categoria,
    )

    return list(db.scalars(stmt).all())


def crear_categoria(
    db: Session,
    categoria: Categoria,
) -> Categoria:

    db.add(categoria)

    try:
        db.commit()
        db.refresh(categoria)
        return categoria

    except IntegrityError:
        db.rollback()
        raise


def actualizar_nombre_categoria(
    db: Session,
    categoria: Categoria,
    nombre_categoria: str,
) -> Categoria:

    categoria.nombre_categoria = nombre_categoria

    try:
        db.commit()
        db.refresh(categoria)
        return categoria

    except IntegrityError:
        db.rollback()
        raise


def cambiar_estado_categoria(
    db: Session,
    categoria: Categoria,
    nuevo_estado: bool,
) -> Categoria:

    categoria.es_activa_categoria = nuevo_estado

    db.commit()
    db.refresh(categoria)

    return categoria


# ============================================================
# SUBCATEGORÍAS
# ============================================================

def obtener_subcategoria_por_id(
    db: Session,
    id_subcategoria: UUID,
    usuario_id: UUID,
) -> Subcategoria | None:
    """
    Obtiene una subcategoría solo cuando la categoría padre
    pertenece al usuario autenticado.
    """

    stmt = (
        select(Subcategoria)
        .join(
            Categoria,
            Subcategoria.categoria_id == Categoria.id_categoria,
        )
        .where(
            Subcategoria.id_subcategoria == id_subcategoria,
            Categoria.usuario_id == usuario_id,
        )
    )

    return db.scalar(stmt)


def obtener_subcategoria_por_nombre(
    db: Session,
    categoria_id: UUID,
    nombre_subcategoria: str,
) -> Subcategoria | None:
    """
    Busca duplicados dentro de una categoría.

    Incluye subcategorías activas e inactivas.
    """

    stmt = select(Subcategoria).where(
        Subcategoria.categoria_id == categoria_id,
        func.lower(Subcategoria.nombre_subcategoria)
        == nombre_subcategoria.lower(),
    )

    return db.scalar(stmt)


def listar_subcategorias(
    db: Session,
    categoria_id: UUID,
    estado: str,
) -> list[Subcategoria]:

    stmt = select(Subcategoria).where(
        Subcategoria.categoria_id == categoria_id
    )

    if estado == "ACTIVA":
        stmt = stmt.where(
            Subcategoria.es_activa_subcategoria.is_(True)
        )

    elif estado == "INACTIVA":
        stmt = stmt.where(
            Subcategoria.es_activa_subcategoria.is_(False)
        )

    stmt = stmt.order_by(
        func.lower(Subcategoria.nombre_subcategoria),
        Subcategoria.id_subcategoria,
    )

    return list(db.scalars(stmt).all())


def crear_subcategoria(
    db: Session,
    subcategoria: Subcategoria,
) -> Subcategoria:

    db.add(subcategoria)

    try:
        db.commit()
        db.refresh(subcategoria)
        return subcategoria

    except IntegrityError:
        db.rollback()
        raise


def actualizar_nombre_subcategoria(
    db: Session,
    subcategoria: Subcategoria,
    nombre_subcategoria: str,
) -> Subcategoria:

    subcategoria.nombre_subcategoria = nombre_subcategoria

    try:
        db.commit()
        db.refresh(subcategoria)
        return subcategoria

    except IntegrityError:
        db.rollback()
        raise


def cambiar_estado_subcategoria(
    db: Session,
    subcategoria: Subcategoria,
    nuevo_estado: bool,
) -> Subcategoria:

    subcategoria.es_activa_subcategoria = nuevo_estado

    db.commit()
    db.refresh(subcategoria)

    return subcategoria