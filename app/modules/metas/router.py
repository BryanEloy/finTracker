from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.modules.metas import service
from app.modules.metas.model import (
    EstadoMeta,
    TipoAsignacion,
)
from app.modules.metas.schemas import (
    AsignacionCrearEntrada,
    AsignacionListaSalida,
    AsignacionSalida,
    MetaActualizarEntrada,
    MetaCierreEntrada,
    MetaCrearEntrada,
    MetaDetalleSalida,
    MetaListaSalida,
    MetaSalida,
)
from app.modules.usuarios.model import Usuario


router = APIRouter(
    prefix="/metas",
    tags=["Metas"],
)


# ============================================================
# CREAR META
# ============================================================

@router.post(
    "",
    response_model=MetaSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_meta(
    datos: MetaCrearEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.crear_meta(
            db=db,
            usuario_id=usuario.id_usuario,
            cuenta_id=datos.cuenta_id,
            nombre_meta=datos.nombre_meta,
            monto_objetivo_meta=datos.monto_objetivo_meta,
            fecha_limite_meta=datos.fecha_limite_meta,
            descripcion_meta=datos.descripcion_meta,
        )

    except service.CuentaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="CUENTA_NO_ENCONTRADA",
        )

    except service.CuentaInactivaError:
        raise HTTPException(
            status_code=409,
            detail="CUENTA_INACTIVA",
        )

    except service.NombreMetaDuplicadoError:
        raise HTTPException(
            status_code=409,
            detail="NOMBRE_META_DUPLICADO",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=422,
            detail="DATOS_INVALIDOS",
        )


# ============================================================
# LISTAR METAS
# ============================================================

@router.get(
    "",
    response_model=MetaListaSalida,
)
def listar_metas(
    estado: str = Query("ACTIVA"),
    cuenta_id: UUID | None = Query(None),
    limite: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    # TODAS significa que no filtramos por estado.
    if estado == "TODAS":
        estado_filtro = None
    else:
        try:
            estado_filtro = EstadoMeta(estado)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="FILTRO_INVALIDO",
            )

    try:
        metas, total = service.listar_metas(
            db=db,
            usuario_id=usuario.id_usuario,
            estado=estado_filtro,
            cuenta_id=cuenta_id,
            limite=limite,
            offset=offset,
        )

        return {
            "metas": metas,
            "total": total,
            "limite": limite,
            "offset": offset,
        }

    except service.CuentaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="CUENTA_NO_ENCONTRADA",
        )


# ============================================================
# CONSULTAR META
# ============================================================

@router.get(
    "/{id_meta}",
    response_model=MetaDetalleSalida,
)
def obtener_meta(
    id_meta: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.obtener_detalle_meta(
            db=db,
            usuario_id=usuario.id_usuario,
            id_meta=id_meta,
        )

    except service.MetaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="META_NO_ENCONTRADA",
        )


# ============================================================
# EDITAR META
# ============================================================

@router.patch(
    "/{id_meta}",
    response_model=MetaSalida,
)
def actualizar_meta(
    id_meta: UUID,
    datos: MetaActualizarEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.actualizar_meta(
            db=db,
            usuario_id=usuario.id_usuario,
            id_meta=id_meta,
            datos=datos,
        )

    except service.MetaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="META_NO_ENCONTRADA",
        )

    except service.MetaCerradaError:
        raise HTTPException(
            status_code=409,
            detail="META_CERRADA",
        )

    except service.NombreMetaDuplicadoError:
        raise HTTPException(
            status_code=409,
            detail="NOMBRE_META_DUPLICADO",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=422,
            detail="DATOS_INVALIDOS",
        )


# ============================================================
# CERRAR META
# ============================================================

@router.post(
    "/{id_meta}/cierre",
    response_model=MetaSalida,
)
def cerrar_meta(
    id_meta: UUID,
    datos: MetaCierreEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.cerrar_meta(
            db=db,
            usuario_id=usuario.id_usuario,
            id_meta=id_meta,
            accion=datos.accion,
        )

    except service.MetaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="META_NO_ENCONTRADA",
        )

    except service.MetaNoFinalizableError:
        raise HTTPException(
            status_code=409,
            detail="META_NO_FINALIZABLE",
        )

    except service.MetaCerradaError:
        raise HTTPException(
            status_code=409,
            detail="META_CERRADA",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=422,
            detail="DATOS_INVALIDOS",
        )


# ============================================================
# CREAR ASIGNACIÓN
# ============================================================

@router.post(
    "/{id_meta}/asignaciones",
    response_model=AsignacionSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_asignacion(
    id_meta: UUID,
    datos: AsignacionCrearEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return service.crear_asignacion(
            db=db,
            usuario_id=usuario.id_usuario,
            id_meta=id_meta,
            tipo_asignacion=datos.tipo_asignacion,
            monto_asignacion=datos.monto_asignacion,
            comentario_asignacion=
                datos.comentario_asignacion,
        )

    except service.UsuarioDesactivadoError:
        raise HTTPException(
            status_code=403,
            detail="USUARIO_DESACTIVADO",
        )

    except service.MetaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="META_NO_ENCONTRADA",
        )

    except service.MetaCerradaError:
        raise HTTPException(
            status_code=409,
            detail="META_CERRADA",
        )

    except service.MetaVencidaError:
        raise HTTPException(
            status_code=409,
            detail="META_VENCIDA",
        )

    except service.CuentaInactivaError:
        raise HTTPException(
            status_code=409,
            detail="CUENTA_INACTIVA",
        )

    except service.FondosLibresInsuficientesError:
        raise HTTPException(
            status_code=409,
            detail="FONDOS_LIBRES_INSUFICIENTES",
        )

    except service.AporteSuperaObjetivoError:
        raise HTTPException(
            status_code=409,
            detail="APORTE_SUPERA_OBJETIVO",
        )

    except service.RetiroSuperaAcumuladoError:
        raise HTTPException(
            status_code=409,
            detail="RETIRO_SUPERA_ACUMULADO",
        )

    except service.DatosInvalidosError:
        raise HTTPException(
            status_code=422,
            detail="DATOS_INVALIDOS",
        )


# ============================================================
# LISTAR ASIGNACIONES
# ============================================================

@router.get(
    "/{id_meta}/asignaciones",
    response_model=AsignacionListaSalida,
)
def listar_asignaciones(
    id_meta: UUID,
    tipo_asignacion: TipoAsignacion | None = Query(None),
    limite: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        asignaciones, total = (
            service.listar_asignaciones(
                db=db,
                usuario_id=usuario.id_usuario,
                id_meta=id_meta,
                tipo_asignacion=tipo_asignacion,
                limite=limite,
                offset=offset,
            )
        )

        return {
            "asignaciones": asignaciones,
            "total": total,
            "limite": limite,
            "offset": offset,
        }

    except service.MetaNoEncontradaError:
        raise HTTPException(
            status_code=404,
            detail="META_NO_ENCONTRADA",
        )