import re
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.cuentas import repository
from app.modules.cuentas.model import Cuenta, TipoCuenta
from app.modules.cuentas.schemas import (
    CuentaActualizarEntrada,
    CuentaCrearEntrada,
    CuentaEstadoSalida,
    CuentaListaItem,
    CuentaListaSalida,
    CuentaPublica,
    EstadoCuenta,
    OperacionCuenta,
)
from app.modules.usuarios.model import Usuario


class CuentaNoEncontradaError(Exception):
    pass


class NombreCuentaDuplicadoError(Exception):
    pass


class DatosCuentaInvalidosError(Exception):
    pass


class LimiteCreditoInvalidoError(Exception):
    pass


class SaldoInicialBloqueadoError(Exception):
    pass

class EstadoFinancieroCuentaNoDisponibleError(Exception):
    pass


def normalizar_texto(
    valor: str | None,
) -> str | None:

    if valor is None:
        return None

    valor = valor.strip()

    return valor if valor else None


def normalizar_numero_cuenta(
    numero: str | None,
) -> str | None:

    if numero is None:
        return None

    numero = (
        numero
        .replace(" ", "")
        .replace("-", "")
    )

    if not re.fullmatch(r"[0-9]{4,30}", numero):
        raise DatosCuentaInvalidosError()

    return numero


def enmascarar_numero_cuenta(
    numero: str | None,
) -> str | None:

    if numero is None:
        return None

    if len(numero) <= 4:
        return numero

    return (
        "*" * (len(numero) - 4)
        + numero[-4:]
    )


def validar_credito(
    tipo_cuenta: TipoCuenta,
    saldo_inicial: Decimal,
    limite_credito: Decimal | None,
) -> None:

    if tipo_cuenta == TipoCuenta.CREDITO:

        if limite_credito is None:
            raise LimiteCreditoInvalidoError()

        if limite_credito <= 0:
            raise LimiteCreditoInvalidoError()

        if saldo_inicial > limite_credito:
            raise LimiteCreditoInvalidoError()

    else:

        if limite_credito is not None:
            raise LimiteCreditoInvalidoError()


def construir_cuenta_publica(
    cuenta: Cuenta,
    estado_financiero: dict,
) -> CuentaPublica:

    return CuentaPublica(
        id_cuenta=cuenta.id_cuenta,
        nombre_cuenta=cuenta.nombre_cuenta,
        tipo_cuenta=cuenta.tipo_cuenta,
        institucion_cuenta=cuenta.institucion_cuenta,
        numero_cuenta_enmascarado=enmascarar_numero_cuenta(
            cuenta.numero_cuenta
        ),
        es_activa_cuenta=cuenta.es_activa_cuenta,
        fecha_creacion_cuenta=cuenta.fecha_creacion_cuenta,
        saldo_inicial_cuenta=cuenta.saldo_inicial_cuenta,
        saldo_actual_cuenta=estado_financiero[
            "saldo_actual_cuenta"
        ],
        limite_credito_cuenta=cuenta.limite_credito_cuenta,
        credito_utilizado_cuenta=estado_financiero[
            "credito_utilizado_cuenta"
        ],
        reserva_total_cuenta=estado_financiero[
            "reserva_total_cuenta"
        ],
        dinero_libre_cuenta=estado_financiero[
            "dinero_libre_cuenta"
        ],
        saldo_disponible_credito_cuenta=estado_financiero[
            "saldo_disponible_credito_cuenta"
        ],
        porcentaje_utilizacion_credito_cuenta=estado_financiero[
            "porcentaje_utilizacion_credito_cuenta"
        ],
    )


def registrar_cuenta(
    db: Session,
    usuario: Usuario,
    datos: CuentaCrearEntrada,
) -> CuentaPublica:

    nombre = datos.nombre_cuenta.strip()

    if len(nombre) < 2:
        raise DatosCuentaInvalidosError()

    institucion = normalizar_texto(
        datos.institucion_cuenta
    )

    numero = normalizar_numero_cuenta(
        datos.numero_cuenta
    )

    validar_credito(
        datos.tipo_cuenta,
        datos.saldo_inicial_cuenta,
        datos.limite_credito_cuenta,
    )

    try:
        repository.bloquear_usuario_v11(
            db,
            usuario.id_usuario,
        )

        cuenta_existente = repository.obtener_por_nombre(
            db,
            usuario.id_usuario,
            nombre,
        )

        if cuenta_existente is not None:
            raise NombreCuentaDuplicadoError()

        cuenta = Cuenta(
            usuario_id=usuario.id_usuario,
            nombre_cuenta=nombre,
            tipo_cuenta=datos.tipo_cuenta,
            institucion_cuenta=institucion,
            numero_cuenta=numero,
            saldo_inicial_cuenta=datos.saldo_inicial_cuenta,
            limite_credito_cuenta=datos.limite_credito_cuenta,
        )

        cuenta = repository.crear(
            db,
            cuenta,
        )

        db.commit()

    except IntegrityError:
        db.rollback()
        raise NombreCuentaDuplicadoError()

    except Exception:
        db.rollback()
        raise

    estado_financiero = (
        repository.obtener_estado_financiero_cuenta(
            db,
            cuenta.id_cuenta,
            usuario.id_usuario,
        )
    )

    if estado_financiero is None:
        raise EstadoFinancieroCuentaNoDisponibleError()

    return construir_cuenta_publica(
        cuenta,
        estado_financiero,
    )


def listar_cuentas(
    db: Session,
    usuario: Usuario,
    estado: EstadoCuenta,
    operacion: OperacionCuenta | None,
) -> CuentaListaSalida:

    cuentas = repository.listar(
        db,
        usuario.id_usuario,
    )

    if estado == EstadoCuenta.ACTIVA:
        cuentas = [
            cuenta
            for cuenta in cuentas
            if cuenta.es_activa_cuenta
        ]

    elif estado == EstadoCuenta.INACTIVA:
        cuentas = [
            cuenta
            for cuenta in cuentas
            if not cuenta.es_activa_cuenta
        ]

    if operacion is not None:
        cuentas = [
            cuenta
            for cuenta in cuentas
            if cuenta_es_elegible(
                cuenta,
                operacion,
            )
        ]

    estados_financieros = (
        repository.listar_estados_financieros_cuentas(
            db,
            usuario.id_usuario,
        )
    )

    items = []

    for cuenta in cuentas:
        datos = estados_financieros.get(
            cuenta.id_cuenta
        )

        if datos is None:
            raise EstadoFinancieroCuentaNoDisponibleError()

        items.append(
            CuentaListaItem(
                id_cuenta=cuenta.id_cuenta,
                nombre_cuenta=cuenta.nombre_cuenta,
                tipo_cuenta=cuenta.tipo_cuenta,
                institucion_cuenta=cuenta.institucion_cuenta,
                numero_cuenta_enmascarado=(
                    enmascarar_numero_cuenta(
                        cuenta.numero_cuenta
                    )
                ),
                es_activa_cuenta=cuenta.es_activa_cuenta,
                saldo_actual_cuenta=datos[
                    "saldo_actual_cuenta"
                ],
                credito_utilizado_cuenta=datos[
                    "credito_utilizado_cuenta"
                ],
                reserva_total_cuenta=datos[
                    "reserva_total_cuenta"
                ],
                dinero_libre_cuenta=datos[
                    "dinero_libre_cuenta"
                ],
                saldo_disponible_credito_cuenta=datos[
                    "saldo_disponible_credito_cuenta"
                ],
                porcentaje_utilizacion_credito_cuenta=datos[
                    "porcentaje_utilizacion_credito_cuenta"
                ],
            )
        )

    return CuentaListaSalida(
        cuentas=items,
        total=len(items),
    )


def cuenta_es_elegible(
    cuenta: Cuenta,
    operacion: OperacionCuenta,
) -> bool:

    if not cuenta.es_activa_cuenta:
        return False

    if operacion == OperacionCuenta.GASTO:
        return cuenta.tipo_cuenta in {
            TipoCuenta.EFECTIVO,
            TipoCuenta.DEBITO,
            TipoCuenta.CREDITO,
        }

    if (
        operacion
        == OperacionCuenta.TRANSFERENCIA_ORIGEN
    ):
        return cuenta.tipo_cuenta in {
            TipoCuenta.EFECTIVO,
            TipoCuenta.DEBITO,
            TipoCuenta.AHORRO,
        }

    if (
        operacion
        == OperacionCuenta.TRANSFERENCIA_DESTINO
    ):
        return True

    if operacion == OperacionCuenta.INGRESO:
        return cuenta.tipo_cuenta in {
            TipoCuenta.EFECTIVO,
            TipoCuenta.DEBITO,
            TipoCuenta.AHORRO,
        }

    return False



def obtener_cuenta(
    db: Session,
    usuario: Usuario,
    id_cuenta,
) -> CuentaPublica:

    cuenta = repository.obtener_por_id(
        db,
        id_cuenta,
        usuario.id_usuario,
    )

    if cuenta is None:
        raise CuentaNoEncontradaError()

    estado_financiero = (
        repository.obtener_estado_financiero_cuenta(
            db,
            cuenta.id_cuenta,
            usuario.id_usuario,
        )
    )

    if estado_financiero is None:
        raise EstadoFinancieroCuentaNoDisponibleError()

    return construir_cuenta_publica(
        cuenta,
        estado_financiero,
    )


def actualizar_cuenta(
    db: Session,
    usuario: Usuario,
    id_cuenta,
    datos: CuentaActualizarEntrada,
) -> CuentaPublica:

    cambios = datos.model_dump(
        exclude_unset=True
    )

    # Validaciones independientes de la base de datos
    if "nombre_cuenta" in cambios:
        nombre = cambios["nombre_cuenta"]

        if nombre is None or len(nombre.strip()) < 2:
            raise DatosCuentaInvalidosError()

        cambios["nombre_cuenta"] = nombre.strip()

    if "institucion_cuenta" in cambios:
        cambios["institucion_cuenta"] = normalizar_texto(
            cambios["institucion_cuenta"]
        )

    if "numero_cuenta" in cambios:
        cambios["numero_cuenta"] = normalizar_numero_cuenta(
            cambios["numero_cuenta"]
        )

    if (
        "saldo_inicial_cuenta" in cambios
        and cambios["saldo_inicial_cuenta"] is None
    ):
        raise DatosCuentaInvalidosError()

    try:
        # 1. Bloquear usuario antes de consultar y modificar
        repository.bloquear_usuario_v11(
            db,
            usuario.id_usuario,
        )

        # 2. Obtener cuenta del usuario autenticado
        cuenta = repository.obtener_por_id(
            db,
            id_cuenta,
            usuario.id_usuario,
        )

        if cuenta is None:
            raise CuentaNoEncontradaError()

        # 3. Validar nombre duplicado
        if "nombre_cuenta" in cambios:
            otra = repository.obtener_por_nombre(
                db,
                usuario.id_usuario,
                cambios["nombre_cuenta"],
            )

            if (
                otra is not None
                and otra.id_cuenta != cuenta.id_cuenta
            ):
                raise NombreCuentaDuplicadoError()

        # 4. Proteger el saldo inicial
        if "saldo_inicial_cuenta" in cambios:

            saldo_nuevo = cambios["saldo_inicial_cuenta"]

            if saldo_nuevo != cuenta.saldo_inicial_cuenta:
                tiene_movimientos = (
                    repository.cuenta_tiene_transacciones(
                        db,
                        cuenta.id_cuenta,
                        usuario.id_usuario,
                    )
                )

                if tiene_movimientos:
                    raise SaldoInicialBloqueadoError()

        # 5. Validar valores finales de la cuenta
        nuevo_saldo = cambios.get(
            "saldo_inicial_cuenta",
            cuenta.saldo_inicial_cuenta,
        )

        nuevo_limite = cambios.get(
            "limite_credito_cuenta",
            cuenta.limite_credito_cuenta,
        )

        validar_credito(
            cuenta.tipo_cuenta,
            nuevo_saldo,
            nuevo_limite,
        )

        # 6. Validar crédito utilizado real
        if cuenta.tipo_cuenta == TipoCuenta.CREDITO:

            estado_financiero = (
                repository.obtener_estado_financiero_cuenta(
                    db,
                    cuenta.id_cuenta,
                    usuario.id_usuario,
                )
            )

            if estado_financiero is None:
                raise EstadoFinancieroCuentaNoDisponibleError()

            credito_utilizado = estado_financiero[
                "credito_utilizado_cuenta"
            ]

            if credito_utilizado is None:
                raise EstadoFinancieroCuentaNoDisponibleError()

            if nuevo_limite < credito_utilizado:
                raise LimiteCreditoInvalidoError()

        # 7. Aplicar cambios
        if cambios:
            cuenta = repository.actualizar(
                db,
                cuenta,
                cambios,
            )

        # 8. Confirmar transacción
        db.commit()

    except IntegrityError:
        db.rollback()
        raise DatosCuentaInvalidosError()

    except Exception:
        db.rollback()
        raise

    # 9. Consultar valores financieros confirmados
    return obtener_cuenta(
        db,
        usuario,
        id_cuenta,
    )


def cambiar_estado_cuenta(
    db: Session,
    usuario: Usuario,
    id_cuenta,
    es_activa: bool,
) -> CuentaEstadoSalida:

    try:
        repository.bloquear_usuario_v11(
            db,
            usuario.id_usuario,
        )

        cuenta = repository.obtener_por_id(
            db,
            id_cuenta,
            usuario.id_usuario,
        )

        if cuenta is None:
            raise CuentaNoEncontradaError()

        if cuenta.es_activa_cuenta != es_activa:
            cuenta = repository.cambiar_estado(
                db,
                cuenta,
                es_activa,
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return CuentaEstadoSalida(
        id_cuenta=cuenta.id_cuenta,
        es_activa_cuenta=cuenta.es_activa_cuenta,
    )
