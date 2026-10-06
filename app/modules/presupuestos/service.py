from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.categorias.model import Categoria
from app.modules.presupuestos import repository
from app.modules.presupuestos.model import (
    DetallePresupuesto,
    EstadoPresupuesto,
    Presupuesto,
)
from app.modules.presupuestos.schemas import (
    AccionCierrePresupuesto,
    PresupuestoCrearEntrada,
)


# ============================================================
# CONSTANTES
# ============================================================

ZONA_NEGOCIO = ZoneInfo("America/Mexico_City")

CERO = Decimal("0.00")
CIEN = Decimal("100.00")


# ============================================================
# EXCEPCIONES
# ============================================================

class UsuarioDesactivadoError(Exception):
    pass


class PresupuestoNoEncontradoError(Exception):
    pass


class CategoriaNoEncontradaError(Exception):
    pass


class CategoriaInactivaError(Exception):
    pass


class PresupuestoActivoExistenteError(Exception):
    pass


class PresupuestoNoFinalizableError(Exception):
    pass


class PresupuestoCerradoError(Exception):
    pass


class DatosInvalidosError(Exception):
    pass


class DistribucionInvalidaError(Exception):
    pass


class DistribucionNoRepresentableError(Exception):
    pass


# ============================================================
# HELPERS GENERALES
# ============================================================

def decimal_dos(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def obtener_valor_enum(valor):
    return getattr(valor, "value", valor)


def usuario_esta_activo(usuario) -> bool:
    return bool(usuario.es_activo_usuario)


def categoria_esta_activa(categoria) -> bool:
    return bool(categoria.es_activa_categoria)


def presupuesto_esta_activo(
    presupuesto: Presupuesto,
) -> bool:
    return (
        obtener_valor_enum(
            presupuesto.estado_presupuesto
        )
        == EstadoPresupuesto.ACTIVO.value
    )


def ahora_negocio() -> datetime:
    return datetime.now(ZONA_NEGOCIO)


# ============================================================
# VENTANA TEMPORAL
# ============================================================

def inicio_dia_siguiente(fecha: date) -> datetime:
    """
    La fecha_fin_presupuesto es inclusiva.

    Ejemplo:
        fecha_fin = 2026-10-31

    El fin exclusivo será:
        2026-11-01 00:00:00 America/Mexico_City
    """

    dia_siguiente = fecha + timedelta(days=1)

    return datetime.combine(
        dia_siguiente,
        time.min,
        tzinfo=ZONA_NEGOCIO,
    )


def obtener_fin_exclusivo(
    presupuesto: Presupuesto,
) -> datetime:
    """
    ACTIVO:
        utiliza el final programado.

    FINALIZADO:
        utiliza el final programado.

    CANCELADO:
        utiliza MIN(fecha_cierre, final programado).
    """

    fin_programado = inicio_dia_siguiente(
        presupuesto.fecha_fin_presupuesto
    )

    estado = obtener_valor_enum(
        presupuesto.estado_presupuesto
    )

    if (
        estado == EstadoPresupuesto.CANCELADO.value
        and presupuesto.fecha_cierre_presupuesto is not None
    ):
        return min(
            presupuesto.fecha_cierre_presupuesto,
            fin_programado,
        )

    return fin_programado


def esta_vencido(
    presupuesto: Presupuesto,
    ahora: datetime | None = None,
) -> bool:
    """
    periodo_vencido solamente puede ser True
    mientras el presupuesto siga ACTIVO.
    """

    if not presupuesto_esta_activo(presupuesto):
        return False

    if ahora is None:
        ahora = ahora_negocio()

    return ahora >= inicio_dia_siguiente(
        presupuesto.fecha_fin_presupuesto
    )


# ============================================================
# REPARTO EXACTO DE CENTAVOS
# ============================================================

def calcular_limites_por_categoria(
    monto_limite: Decimal,
    detalles,
) -> dict[UUID, Decimal]:
    """
    Reparte exactamente el límite global utilizando
    el método de restos mayores.

    Desempate:
        categoria_id ASC
    """

    monto_limite = Decimal(monto_limite)

    centavos_totales = int(
        monto_limite * Decimal("100")
    )

    calculos = []

    for detalle in detalles:
        porcentaje = (
            detalle.porcentaje_asignado_presupuesto
        )

        cuota_exacta = (
            Decimal(centavos_totales)
            * Decimal(porcentaje)
            / CIEN
        )

        centavos_base = int(
            cuota_exacta.to_integral_value(
                rounding=ROUND_DOWN
            )
        )

        resto = (
            cuota_exacta
            - Decimal(centavos_base)
        )

        calculos.append(
            {
                "categoria_id":
                    detalle.categoria_id,

                "centavos":
                    centavos_base,

                "resto":
                    resto,
            }
        )

    centavos_asignados = sum(
        item["centavos"]
        for item in calculos
    )

    centavos_restantes = (
        centavos_totales
        - centavos_asignados
    )

    # Mayor resto primero.
    # En empate, categoria_id ASC.
    orden_resto = sorted(
        calculos,
        key=lambda item: (
            -item["resto"],
            str(item["categoria_id"]),
        ),
    )

    for indice in range(centavos_restantes):
        orden_resto[indice]["centavos"] += 1

    resultado = {
        item["categoria_id"]: (
            Decimal(item["centavos"])
            / Decimal("100")
        )
        for item in calculos
    }

    # Ninguna categoría puede recibir $0.00.
    if any(
        monto < Decimal("0.01")
        for monto in resultado.values()
    ):
        raise DistribucionNoRepresentableError()

    # Comprobación defensiva:
    # la suma debe ser exactamente el límite global.
    suma = sum(
        resultado.values(),
        CERO,
    )

    if suma != monto_limite:
        raise DistribucionNoRepresentableError()

    return resultado


# ============================================================
# INDICADORES Y MÉTRICAS
# ============================================================

def calcular_indicador(
    consumo: Decimal,
    limite: Decimal,
    porcentaje_alerta: int,
) -> str:
    """
    OK:
        consumo < umbral

    ALERTA:
        consumo >= umbral
        y consumo <= límite

    EXCEDIDO:
        consumo > límite
    """

    consumo = Decimal(consumo)
    limite = Decimal(limite)

    if consumo > limite:
        return "EXCEDIDO"

    monto_alerta = (
        limite
        * Decimal(porcentaje_alerta)
        / CIEN
    )

    if consumo >= monto_alerta:
        return "ALERTA"

    return "OK"


def calcular_metricas(
    consumo: Decimal,
    limite: Decimal,
    porcentaje_alerta: int,
):
    consumo = Decimal(consumo)
    limite = Decimal(limite)

    restante = max(
        limite - consumo,
        CERO,
    )

    excedido = max(
        consumo - limite,
        CERO,
    )

    porcentaje = (
        consumo
        / limite
        * CIEN
    )

    return {
        "consumo":
            decimal_dos(consumo),

        "restante":
            decimal_dos(restante),

        "excedido":
            decimal_dos(excedido),

        "porcentaje":
            decimal_dos(porcentaje),

        "indicador":
            calcular_indicador(
                consumo=consumo,
                limite=limite,
                porcentaje_alerta=porcentaje_alerta,
            ),
    }


# ============================================================
# CONSTRUIR RESUMEN
# ============================================================

def construir_resumen(
    db: Session,
    presupuesto: Presupuesto,
    consumo_total: Decimal | None = None,
):
    """
    Si consumo_total ya fue calculado por construir_detalle(),
    se reutiliza para evitar realizar una segunda lectura
    independiente de las transacciones.
    """

    if consumo_total is None:
        fin_exclusivo = obtener_fin_exclusivo(
            presupuesto
        )

        consumo_total = (
            repository.calcular_consumo_total(
                db=db,
                usuario_id=presupuesto.usuario_id,
                inicio=(
                    presupuesto
                    .fecha_inicio_presupuesto
                ),
                fin_exclusivo=fin_exclusivo,
            )
        )

    metricas = calcular_metricas(
        consumo=consumo_total,
        limite=Decimal(
            presupuesto.monto_limite_presupuesto
        ),
        porcentaje_alerta=80,
    )

    return {
        "id_presupuesto":
            presupuesto.id_presupuesto,

        "fecha_inicio_presupuesto":
            presupuesto.fecha_inicio_presupuesto,

        "fecha_fin_presupuesto":
            presupuesto.fecha_fin_presupuesto,

        "fecha_cierre_presupuesto":
            presupuesto.fecha_cierre_presupuesto,

        "estado_presupuesto":
            presupuesto.estado_presupuesto,

        "monto_limite_presupuesto":
            decimal_dos(
                presupuesto.monto_limite_presupuesto
            ),

        "monto_consumido_presupuesto":
            metricas["consumo"],

        "monto_restante_presupuesto":
            metricas["restante"],

        "monto_excedido_presupuesto":
            metricas["excedido"],

        "porcentaje_consumido_presupuesto":
            metricas["porcentaje"],

        "indicador_presupuesto":
            metricas["indicador"],

        "periodo_vencido":
            esta_vencido(presupuesto),
    }


# ============================================================
# CONSTRUIR DETALLE COMPLETO
# ============================================================

def construir_detalle(
    db: Session,
    presupuesto: Presupuesto,
):
    fin_exclusivo = obtener_fin_exclusivo(
        presupuesto
    )

    filas_detalles = (
        repository.obtener_detalles_presupuesto(
            db=db,
            id_presupuesto=(
                presupuesto.id_presupuesto
            ),
        )
    )

    # Una sola consulta obtiene el consumo agrupado
    # por categoría.
    consumos_categoria = (
        repository.calcular_consumos_por_categoria(
            db=db,
            usuario_id=presupuesto.usuario_id,
            inicio=(
                presupuesto.fecha_inicio_presupuesto
            ),
            fin_exclusivo=fin_exclusivo,
        )
    )

    limites_categoria = (
        calcular_limites_por_categoria(
            monto_limite=Decimal(
                presupuesto.monto_limite_presupuesto
            ),
            detalles=[
                fila[0]
                for fila in filas_detalles
            ],
        )
    )

    detalles_salida = []

    consumo_presupuestado = CERO

    for detalle, nombre_categoria in filas_detalles:
        consumo = consumos_categoria.get(
            detalle.categoria_id,
            CERO,
        )

        limite_categoria = (
            limites_categoria[
                detalle.categoria_id
            ]
        )

        consumo_presupuestado += consumo

        metricas = calcular_metricas(
            consumo=consumo,
            limite=limite_categoria,
            porcentaje_alerta=(
                detalle
                .porcentaje_alerta_presupuesto
            ),
        )

        detalles_salida.append(
            {
                "id_detalle_presupuesto":
                    detalle.id_detalle_presupuesto,

                "categoria_id":
                    detalle.categoria_id,

                "nombre_categoria":
                    nombre_categoria,

                "porcentaje_asignado_presupuesto":
                    detalle
                    .porcentaje_asignado_presupuesto,

                "porcentaje_alerta_presupuesto":
                    detalle
                    .porcentaje_alerta_presupuesto,

                "monto_limite_categoria":
                    decimal_dos(
                        limite_categoria
                    ),

                "monto_consumido_categoria":
                    metricas["consumo"],

                "monto_restante_categoria":
                    metricas["restante"],

                "monto_excedido_categoria":
                    metricas["excedido"],

                "porcentaje_consumido_categoria":
                    metricas["porcentaje"],

                "indicador_categoria":
                    metricas["indicador"],
            }
        )

    # Como consumos_categoria contiene TODOS los gastos
    # agrupados por categoría, su suma es el consumo global.
    consumo_total = sum(
        consumos_categoria.values(),
        CERO,
    )

    consumo_no_presupuestado = max(
        consumo_total - consumo_presupuestado,
        CERO,
    )

    # Reutilizamos exactamente consumo_total.
    resumen = construir_resumen(
        db=db,
        presupuesto=presupuesto,
        consumo_total=consumo_total,
    )

    return {
        "presupuesto":
            resumen,

        "monto_consumido_presupuestado":
            decimal_dos(
                consumo_presupuestado
            ),

        "monto_consumido_no_presupuestado":
            decimal_dos(
                consumo_no_presupuestado
            ),

        "detalles":
            detalles_salida,
    }


# ============================================================
# CREAR PRESUPUESTO
# ============================================================

def crear_presupuesto(
    db: Session,
    usuario_id: UUID,
    datos: PresupuestoCrearEntrada,
):
    try:
        # ----------------------------------------------------
        # 1. LOCK USUARIO
        # ----------------------------------------------------

        usuario = repository.bloquear_usuario(
            db=db,
            usuario_id=usuario_id,
        )

        if (
            usuario is None
            or not usuario_esta_activo(usuario)
        ):
            raise UsuarioDesactivadoError()

        # ----------------------------------------------------
        # 2. COMPROBAR PRESUPUESTO ACTIVO
        # ----------------------------------------------------

        existente = (
            repository.obtener_presupuesto_activo(
                db=db,
                usuario_id=usuario_id,
            )
        )

        if existente is not None:
            raise PresupuestoActivoExistenteError()

        # ----------------------------------------------------
        # 3. VALIDACIÓN DEFENSIVA DE DISTRIBUCIÓN
        # ----------------------------------------------------

        if (
            len(datos.detalles) < 1
            or len(datos.detalles) > 100
        ):
            raise DistribucionInvalidaError()

        categorias_ids = [
            detalle.categoria_id
            for detalle in datos.detalles
        ]

        if len(categorias_ids) != len(
            set(categorias_ids)
        ):
            raise DistribucionInvalidaError()

        suma_porcentajes = sum(
            detalle.porcentaje_asignado_presupuesto
            for detalle in datos.detalles
        )

        if suma_porcentajes != 100:
            raise DistribucionInvalidaError()

        # ----------------------------------------------------
        # 4. LOCK CATEGORÍAS EN ORDEN
        # ----------------------------------------------------

        categorias = repository.bloquear_categorias(
            db=db,
            usuario_id=usuario_id,
            categorias_ids=categorias_ids,
        )

        categorias_por_id = {
            categoria.id_categoria: categoria
            for categoria in categorias
        }

        # Categoría inexistente o ajena.
        if len(categorias_por_id) != len(
            categorias_ids
        ):
            raise CategoriaNoEncontradaError()

        # ----------------------------------------------------
        # 5. COMPROBAR ACTIVIDAD
        # ----------------------------------------------------

        for categoria_id in sorted(
            categorias_por_id,
            key=str,
        ):
            categoria = (
                categorias_por_id[
                    categoria_id
                ]
            )

            if not categoria_esta_activa(
                categoria
            ):
                raise CategoriaInactivaError()

        # ----------------------------------------------------
        # 6. OBTENER INSTANTE DE CREACIÓN
        #
        # IMPORTANTE:
        # después de adquirir los locks.
        # ----------------------------------------------------

        ahora = ahora_negocio()
        hoy = ahora.date()

        if (
            datos.fecha_fin_presupuesto < hoy
            or datos.fecha_fin_presupuesto
            > date(9999, 12, 30)
        ):
            raise DatosInvalidosError()

        # ----------------------------------------------------
        # 7. REPARTO MONETARIO
        # ----------------------------------------------------

        calcular_limites_por_categoria(
            monto_limite=(
                datos.monto_limite_presupuesto
            ),
            detalles=datos.detalles,
        )

        # ----------------------------------------------------
        # 8. INSERT PADRE
        # ----------------------------------------------------

        presupuesto = Presupuesto(
            usuario_id=usuario_id,

            # Usamos exactamente el instante obtenido
            # después de los locks.
            fecha_inicio_presupuesto=ahora,

            fecha_fin_presupuesto=(
                datos.fecha_fin_presupuesto
            ),

            monto_limite_presupuesto=(
                datos.monto_limite_presupuesto
            ),

            estado_presupuesto=(
                EstadoPresupuesto.ACTIVO
            ),
        )

        repository.agregar_presupuesto(
            db=db,
            presupuesto=presupuesto,
        )

        # ----------------------------------------------------
        # 9. INSERT DISTRIBUCIÓN COMPLETA
        # ----------------------------------------------------

        detalles_db = [
            DetallePresupuesto(
                presupuesto_id=(
                    presupuesto.id_presupuesto
                ),

                usuario_id=usuario_id,

                categoria_id=(
                    detalle.categoria_id
                ),

                porcentaje_asignado_presupuesto=(
                    detalle
                    .porcentaje_asignado_presupuesto
                ),

                porcentaje_alerta_presupuesto=(
                    detalle
                    .porcentaje_alerta_presupuesto
                ),
            )
            for detalle in datos.detalles
        ]

        repository.agregar_detalles(
            db=db,
            detalles=detalles_db,
        )

        # ----------------------------------------------------
        # 10. CONSTRUIR RESULTADO CON LOCK AÚN ACTIVO
        # ----------------------------------------------------

        resultado = construir_detalle(
            db=db,
            presupuesto=presupuesto,
        )

        # ----------------------------------------------------
        # 11. COMMIT
        # ----------------------------------------------------

        db.commit()

        return resultado

    except (
        UsuarioDesactivadoError,
        CategoriaNoEncontradaError,
        CategoriaInactivaError,
        PresupuestoActivoExistenteError,
        DatosInvalidosError,
        DistribucionInvalidaError,
        DistribucionNoRepresentableError,
    ):
        db.rollback()
        raise

    except IntegrityError as error:
        db.rollback()

        nombre_constraint = getattr(
            getattr(
                error.orig,
                "diag",
                None,
            ),
            "constraint_name",
            None,
        )

        if (
            nombre_constraint
            == "uq_presupuesto_un_activo_usuario"
        ):
            raise PresupuestoActivoExistenteError()

        if (
            nombre_constraint
            == "uq_detalle_presupuesto_categoria"
        ):
            raise DistribucionInvalidaError()

        raise DatosInvalidosError()


# ============================================================
# LISTAR PRESUPUESTOS
# ============================================================

def listar_presupuestos(
    db: Session,
    usuario_id: UUID,
    estado: EstadoPresupuesto | None,
    limite: int,
    offset: int,
):
    presupuestos, total = (
        repository.listar_presupuestos(
            db=db,
            usuario_id=usuario_id,
            estado=estado,
            limite=limite,
            offset=offset,
        )
    )

    salida = [
        construir_resumen(
            db=db,
            presupuesto=presupuesto,
        )
        for presupuesto in presupuestos
    ]

    return salida, total


# ============================================================
# OBTENER DETALLE
# ============================================================

def obtener_detalle_presupuesto(
    db: Session,
    usuario_id: UUID,
    id_presupuesto: UUID,
):
    presupuesto = (
        repository.obtener_presupuesto_por_id(
            db=db,
            usuario_id=usuario_id,
            id_presupuesto=id_presupuesto,
        )
    )

    if presupuesto is None:
        raise PresupuestoNoEncontradoError()

    return construir_detalle(
        db=db,
        presupuesto=presupuesto,
    )


# ============================================================
# CERRAR PRESUPUESTO
# ============================================================

def cerrar_presupuesto(
    db: Session,
    usuario_id: UUID,
    id_presupuesto: UUID,
    accion: AccionCierrePresupuesto,
):
    try:
        # ----------------------------------------------------
        # 1. LOCK USUARIO
        # ----------------------------------------------------

        usuario = repository.bloquear_usuario(
            db=db,
            usuario_id=usuario_id,
        )

        if (
            usuario is None
            or not usuario_esta_activo(usuario)
        ):
            raise UsuarioDesactivadoError()

        # ----------------------------------------------------
        # 2. LOCK PRESUPUESTO
        # ----------------------------------------------------

        presupuesto = (
            repository.bloquear_presupuesto(
                db=db,
                usuario_id=usuario_id,
                id_presupuesto=id_presupuesto,
            )
        )

        if presupuesto is None:
            raise PresupuestoNoEncontradoError()

        estado = obtener_valor_enum(
            presupuesto.estado_presupuesto
        )

        # ----------------------------------------------------
        # 3. IDEMPOTENCIA
        # ----------------------------------------------------

        if (
            accion
            == AccionCierrePresupuesto.FINALIZAR
            and estado
            == EstadoPresupuesto.FINALIZADO.value
        ):
            resultado = construir_detalle(
                db=db,
                presupuesto=presupuesto,
            )

            db.commit()

            return resultado

        if (
            accion
            == AccionCierrePresupuesto.CANCELAR
            and estado
            == EstadoPresupuesto.CANCELADO.value
        ):
            resultado = construir_detalle(
                db=db,
                presupuesto=presupuesto,
            )

            db.commit()

            return resultado

        # Una acción diferente sobre un presupuesto
        # ya cerrado no es válida.
        if estado != EstadoPresupuesto.ACTIVO.value:
            raise PresupuestoCerradoError()

        # ----------------------------------------------------
        # 4. OBTENER TIEMPO DESPUÉS DE LOS LOCKS
        # ----------------------------------------------------

        ahora = ahora_negocio()

        # ----------------------------------------------------
        # 5. APLICAR CIERRE
        # ----------------------------------------------------

        if (
            accion
            == AccionCierrePresupuesto.FINALIZAR
        ):
            fin_programado = (
                inicio_dia_siguiente(
                    presupuesto
                    .fecha_fin_presupuesto
                )
            )

            if ahora < fin_programado:
                raise PresupuestoNoFinalizableError()

            presupuesto.estado_presupuesto = (
                EstadoPresupuesto.FINALIZADO
            )

        elif (
            accion
            == AccionCierrePresupuesto.CANCELAR
        ):
            presupuesto.estado_presupuesto = (
                EstadoPresupuesto.CANCELADO
            )

        else:
            raise DatosInvalidosError()

        presupuesto.fecha_cierre_presupuesto = ahora

        repository.actualizar_presupuesto(
            db=db,
            presupuesto=presupuesto,
        )

        # ----------------------------------------------------
        # 6. CONSTRUIR RESPUESTA ANTES DEL COMMIT
        # ----------------------------------------------------

        resultado = construir_detalle(
            db=db,
            presupuesto=presupuesto,
        )

        # ----------------------------------------------------
        # 7. COMMIT
        # ----------------------------------------------------

        db.commit()

        return resultado

    except (
        UsuarioDesactivadoError,
        PresupuestoNoEncontradoError,
        PresupuestoNoFinalizableError,
        PresupuestoCerradoError,
        DatosInvalidosError,
    ):
        db.rollback()
        raise


# ============================================================
# LISTAR GASTOS DEL PRESUPUESTO
# ============================================================

def listar_gastos(
    db: Session,
    usuario_id: UUID,
    id_presupuesto: UUID,
    alcance: str,
    categoria_id: UUID | None,
    limite: int,
    offset: int,
):
    # --------------------------------------------------------
    # 1. PRESUPUESTO PROPIO
    # --------------------------------------------------------

    presupuesto = (
        repository.obtener_presupuesto_por_id(
            db=db,
            usuario_id=usuario_id,
            id_presupuesto=id_presupuesto,
        )
    )

    if presupuesto is None:
        raise PresupuestoNoEncontradoError()

    # --------------------------------------------------------
    # 2. FILTRO OPCIONAL DE CATEGORÍA
    # --------------------------------------------------------

    if categoria_id is not None:
        categoria = db.get(
            Categoria,
            categoria_id,
        )

        # No exigimos que esté activa.
        # Solo debe existir y pertenecer al usuario.
        if (
            categoria is None
            or categoria.usuario_id != usuario_id
        ):
            raise CategoriaNoEncontradaError()

    # --------------------------------------------------------
    # 3. VENTANA TEMPORAL
    # --------------------------------------------------------

    fin_exclusivo = obtener_fin_exclusivo(
        presupuesto
    )

    # --------------------------------------------------------
    # 4. CONSULTAR GASTOS
    # --------------------------------------------------------

    return repository.listar_gastos_presupuesto(
        db=db,
        usuario_id=usuario_id,
        id_presupuesto=id_presupuesto,
        inicio=(
            presupuesto.fecha_inicio_presupuesto
        ),
        fin_exclusivo=fin_exclusivo,
        alcance=alcance,
        categoria_id=categoria_id,
        limite=limite,
        offset=offset,
    )