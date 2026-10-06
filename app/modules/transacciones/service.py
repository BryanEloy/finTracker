from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.transacciones import repository
from app.modules.transacciones.model import (
    TipoTransaccion,
    Transaccion,
)


# ============================================================
# EXCEPCIONES
# ============================================================

class CuentaNoEncontradaError(Exception):
    pass

class TransaccionNoEncontradaError(Exception):
    pass

class CuentaInactivaError(Exception):
    pass


class CategoriaNoEncontradaError(Exception):
    pass


class CategoriaInactivaError(Exception):
    pass


class SubcategoriaNoEncontradaError(Exception):
    pass


class SubcategoriaInactivaError(Exception):
    pass


class SaldoInsuficienteError(Exception):
    pass


class LimiteCreditoExcedidoError(Exception):
    pass


class PagoSuperaDeudaError(Exception):
    pass


class DatosInvalidosError(Exception):
    pass


# ============================================================
# AUXILIARES
# ============================================================

def obtener_tipo_cuenta(cuenta) -> str:
    """
    Devuelve el tipo de cuenta como texto independientemente
    de si SQLAlchemy devuelve Enum o str.
    """

    tipo = cuenta.tipo_cuenta

    if hasattr(tipo, "value"):
        return tipo.value

    return str(tipo)


def validar_estructura(
    tipo_transaccion: TipoTransaccion,
    cuenta_id: UUID,
    cuenta_destino_id: UUID | None,
    categoria_id: UUID | None,
    subcategoria_id: UUID | None,
) -> None:

    # --------------------------------------------------------
    # INGRESO
    # --------------------------------------------------------

    if tipo_transaccion == TipoTransaccion.INGRESO:

        if cuenta_destino_id is not None:
            raise DatosInvalidosError()

        if categoria_id is not None:
            raise DatosInvalidosError()

        if subcategoria_id is not None:
            raise DatosInvalidosError()

        return

    # --------------------------------------------------------
    # GASTO
    # --------------------------------------------------------

    if tipo_transaccion == TipoTransaccion.GASTO:

        if cuenta_destino_id is not None:
            raise DatosInvalidosError()

        if categoria_id is None:
            raise DatosInvalidosError()

        return

    # --------------------------------------------------------
    # TRANSFERENCIA
    # --------------------------------------------------------

    if tipo_transaccion == TipoTransaccion.TRANSFERENCIA:

        if cuenta_destino_id is None:
            raise DatosInvalidosError()

        if cuenta_destino_id == cuenta_id:
            raise DatosInvalidosError()

        if categoria_id is not None:
            raise DatosInvalidosError()

        if subcategoria_id is not None:
            raise DatosInvalidosError()

        return

    raise DatosInvalidosError()


def validar_tipo_cuenta(
    tipo_transaccion: TipoTransaccion,
    cuenta,
    cuenta_destino=None,
) -> None:

    tipo_cuenta = obtener_tipo_cuenta(cuenta)

    # INGRESO:
    # EFECTIVO, DEBITO o AHORRO.
    if tipo_transaccion == TipoTransaccion.INGRESO:

        if tipo_cuenta not in {
            "EFECTIVO",
            "DEBITO",
            "AHORRO",
        }:
            raise DatosInvalidosError()

        return

    # GASTO:
    # EFECTIVO, DEBITO o CREDITO.
    if tipo_transaccion == TipoTransaccion.GASTO:

        if tipo_cuenta not in {
            "EFECTIVO",
            "DEBITO",
            "CREDITO",
        }:
            raise DatosInvalidosError()

        return

    # TRANSFERENCIA:
    # origen: EFECTIVO, DEBITO o AHORRO.
    # destino: cualquiera de los cuatro tipos.
    if tipo_transaccion == TipoTransaccion.TRANSFERENCIA:

        if tipo_cuenta not in {
            "EFECTIVO",
            "DEBITO",
            "AHORRO",
        }:
            raise DatosInvalidosError()

        if cuenta_destino is None:
            raise DatosInvalidosError()

        tipo_destino = obtener_tipo_cuenta(
            cuenta_destino
        )

        if tipo_destino not in {
            "EFECTIVO",
            "DEBITO",
            "AHORRO",
            "CREDITO",
        }:
            raise DatosInvalidosError()

        return

    raise DatosInvalidosError()


# ============================================================
# CLASIFICACIÓN
# ============================================================

def validar_clasificacion_gasto(
    db: Session,
    usuario_id: UUID,
    categoria_id: UUID,
    subcategoria_id: UUID | None,
) -> None:

    categoria = repository.obtener_categoria_propia(
        db=db,
        usuario_id=usuario_id,
        id_categoria=categoria_id,
    )

    if not categoria:
        raise CategoriaNoEncontradaError()

    if not categoria.es_activa_categoria:
        raise CategoriaInactivaError()

    if subcategoria_id is None:
        return

    subcategoria = repository.obtener_subcategoria_propia(
        db=db,
        usuario_id=usuario_id,
        id_subcategoria=subcategoria_id,
    )

    if not subcategoria:
        raise SubcategoriaNoEncontradaError()

    # Es propia, pero pertenece a otra categoría.
    if subcategoria.categoria_id != categoria_id:
        raise DatosInvalidosError()

    if not subcategoria.es_activa_subcategoria:
        raise SubcategoriaInactivaError()


# ============================================================
# VALIDACIÓN FINANCIERA
# ============================================================

def validar_gasto(
    db: Session,
    cuenta,
    monto: Decimal,
) -> None:

    tipo_cuenta = obtener_tipo_cuenta(cuenta)

    # --------------------------------------------------------
    # GASTO NO CREDITICIO
    # --------------------------------------------------------

    if tipo_cuenta in {
        "EFECTIVO",
        "DEBITO",
    }:
        saldo_actual = repository.calcular_saldo_actual(
            db=db,
            cuenta=cuenta,
        )

        if monto > saldo_actual:
            raise SaldoInsuficienteError()

        return

    # --------------------------------------------------------
    # GASTO CON CRÉDITO
    # --------------------------------------------------------

    if tipo_cuenta == "CREDITO":

        credito_utilizado = (
            repository.calcular_credito_utilizado(
                db=db,
                cuenta=cuenta,
            )
        )

        limite = Decimal(
            cuenta.limite_credito_cuenta
        )

        if credito_utilizado + monto > limite:
            raise LimiteCreditoExcedidoError()

        return

    raise DatosInvalidosError()


def validar_transferencia(
    db: Session,
    cuenta_origen,
    cuenta_destino,
    monto: Decimal,
) -> None:

    # --------------------------------------------------------
    # ORIGEN
    # --------------------------------------------------------

    saldo_origen = repository.calcular_saldo_actual(
        db=db,
        cuenta=cuenta_origen,
    )

    if monto > saldo_origen:
        raise SaldoInsuficienteError()

    # --------------------------------------------------------
    # DESTINO CREDITO
    # --------------------------------------------------------

    tipo_destino = obtener_tipo_cuenta(
        cuenta_destino
    )

    if tipo_destino == "CREDITO":

        deuda_actual = (
            repository.calcular_credito_utilizado(
                db=db,
                cuenta=cuenta_destino,
            )
        )

        if monto > deuda_actual:
            raise PagoSuperaDeudaError()


# ============================================================
# CREAR TRANSACCIÓN
# ============================================================

def crear_transaccion(
    db: Session,
    usuario_id: UUID,
    tipo_transaccion: TipoTransaccion,
    cuenta_id: UUID,
    cuenta_destino_id: UUID | None,
    categoria_id: UUID | None,
    subcategoria_id: UUID | None,
    monto_transaccion: Decimal,
    comentario_transaccion: str | None,
) -> Transaccion:

    try:
        usuario = repository.bloquear_usuario(
            db=db,
            usuario_id=usuario_id,
        )

        if usuario is None:
            raise DatosInvalidosError()

        if not usuario.es_activo_usuario:
            raise DatosInvalidosError()
        # ----------------------------------------------------
        # 1. ESTRUCTURA DEL MOVIMIENTO
        # ----------------------------------------------------

        validar_estructura(
            tipo_transaccion=tipo_transaccion,
            cuenta_id=cuenta_id,
            cuenta_destino_id=cuenta_destino_id,
            categoria_id=categoria_id,
            subcategoria_id=subcategoria_id,
        )

        # ----------------------------------------------------
        # 2. BLOQUEAR CUENTAS PARTICIPANTES
        # ----------------------------------------------------

        ids_cuentas = [cuenta_id]

        if cuenta_destino_id is not None:
            ids_cuentas.append(cuenta_destino_id)

        cuentas = repository.bloquear_cuentas(
            db=db,
            usuario_id=usuario_id,
            ids_cuentas=ids_cuentas,
        )

        cuenta = cuentas.get(cuenta_id)

        if not cuenta:
            raise CuentaNoEncontradaError()

        cuenta_destino = None

        if cuenta_destino_id is not None:
            cuenta_destino = cuentas.get(
                cuenta_destino_id
            )

            if not cuenta_destino:
                # El contrato final usa CUENTA_NO_ENCONTRADA
                # para cuenta principal o destino.
                raise CuentaNoEncontradaError()

        # ----------------------------------------------------
        # 3. ESTADO DE CUENTAS
        # ----------------------------------------------------

        if not cuenta.es_activa_cuenta:
            raise CuentaInactivaError()

        if (
            cuenta_destino is not None
            and not cuenta_destino.es_activa_cuenta
        ):
            raise CuentaInactivaError()

        # ----------------------------------------------------
        # 4. TIPOS DE CUENTA
        # ----------------------------------------------------

        validar_tipo_cuenta(
            tipo_transaccion=tipo_transaccion,
            cuenta=cuenta,
            cuenta_destino=cuenta_destino,
        )

        # ----------------------------------------------------
        # 5. CATEGORÍA / SUBCATEGORÍA
        # ----------------------------------------------------

        if tipo_transaccion == TipoTransaccion.GASTO:

            # validar_estructura ya garantizó que no sea None.
            validar_clasificacion_gasto(
                db=db,
                usuario_id=usuario_id,
                categoria_id=categoria_id,
                subcategoria_id=subcategoria_id,
            )

        # ----------------------------------------------------
        # 6. REGLAS FINANCIERAS
        # ----------------------------------------------------

        if tipo_transaccion == TipoTransaccion.GASTO:

            validar_gasto(
                db=db,
                cuenta=cuenta,
                monto=monto_transaccion,
            )

        elif (
            tipo_transaccion
            == TipoTransaccion.TRANSFERENCIA
        ):

            validar_transferencia(
                db=db,
                cuenta_origen=cuenta,
                cuenta_destino=cuenta_destino,
                monto=monto_transaccion,
            )

        # INGRESO no necesita comprobar fondos.

        # ----------------------------------------------------
        # 7. INSERT
        # ----------------------------------------------------

        transaccion = Transaccion(
            usuario_id=usuario_id,
            cuenta_id=cuenta_id,
            tipo_transaccion=tipo_transaccion,
            cuenta_destino_id=cuenta_destino_id,
            categoria_id=categoria_id,
            subcategoria_id=subcategoria_id,
            monto_transaccion=monto_transaccion,
            comentario_transaccion=comentario_transaccion,
        )

        repository.agregar_transaccion(
            db=db,
            transaccion=transaccion,
        )

        # ----------------------------------------------------
        # 8. COMMIT ÚNICO
        # ----------------------------------------------------

        db.commit()

        db.refresh(transaccion)

        return transaccion

    except (
        CuentaNoEncontradaError,
        CuentaInactivaError,
        CategoriaNoEncontradaError,
        CategoriaInactivaError,
        SubcategoriaNoEncontradaError,
        SubcategoriaInactivaError,
        SaldoInsuficienteError,
        LimiteCreditoExcedidoError,
        PagoSuperaDeudaError,
        DatosInvalidosError,
    ):
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise DatosInvalidosError()

    except Exception:
        db.rollback()
        raise


# ============================================================
# OBTENER DETALLE
# ============================================================

def obtener_transaccion(
    db: Session,
    usuario_id: UUID,
    id_transaccion: UUID,
) -> Transaccion:

    transaccion = repository.obtener_transaccion_por_id(
        db=db,
        usuario_id=usuario_id,
        id_transaccion=id_transaccion,
    )

    if not transaccion:
        raise TransaccionNoEncontradaError()

    return transaccion


# ============================================================
# LISTAR
# ============================================================

def listar_transacciones(
    db: Session,
    usuario_id: UUID,
    tipo_transaccion: TipoTransaccion | None,
    cuenta_id: UUID | None,
    limite: int,
    offset: int,
) -> tuple[list[Transaccion], int]:

    # Si se proporciona cuenta_id, debe ser una cuenta propia.
    # Puede estar activa o inactiva.
    if cuenta_id is not None:

        cuenta = repository.obtener_cuenta_propia(
            db=db,
            usuario_id=usuario_id,
            id_cuenta=cuenta_id,
        )

        if not cuenta:
            raise CuentaNoEncontradaError()

    return repository.listar_transacciones(
        db=db,
        usuario_id=usuario_id,
        tipo_transaccion=tipo_transaccion,
        cuenta_id=cuenta_id,
        limite=limite,
        offset=offset,
    )