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


def calcular_credito_utilizado(
    cuenta: Cuenta,
) -> Decimal | None:

    if cuenta.tipo_cuenta != TipoCuenta.CREDITO:
        return None

    # Hasta implementar Transacciones:
    return cuenta.saldo_inicial_cuenta


def calcular_saldo_actual(
    cuenta: Cuenta,
) -> Decimal:

    if cuenta.tipo_cuenta == TipoCuenta.CREDITO:
        credito_utilizado = calcular_credito_utilizado(
            cuenta
        )

        return credito_utilizado or Decimal("0")

    # Hasta implementar Transacciones:
    return cuenta.saldo_inicial_cuenta


def construir_cuenta_publica(
    cuenta: Cuenta,
) -> CuentaPublica:

    credito_utilizado = calcular_credito_utilizado(
        cuenta
    )

    saldo_disponible = None
    porcentaje = None

    if cuenta.tipo_cuenta == TipoCuenta.CREDITO:

        saldo_disponible = (
            cuenta.limite_credito_cuenta
            - credito_utilizado
        )

        porcentaje = (
            (
                credito_utilizado
                / cuenta.limite_credito_cuenta
            )
            * Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    return CuentaPublica(
        id_cuenta=cuenta.id_cuenta,
        nombre_cuenta=cuenta.nombre_cuenta,
        tipo_cuenta=cuenta.tipo_cuenta,
        institucion_cuenta=(
            cuenta.institucion_cuenta
        ),
        numero_cuenta_enmascarado=(
            enmascarar_numero_cuenta(
                cuenta.numero_cuenta
            )
        ),
        es_activa_cuenta=(
            cuenta.es_activa_cuenta
        ),
        fecha_creacion_cuenta=(
            cuenta.fecha_creacion_cuenta
        ),
        saldo_inicial_cuenta=(
            cuenta.saldo_inicial_cuenta
        ),
        saldo_actual_cuenta=(
            calcular_saldo_actual(cuenta)
        ),
        limite_credito_cuenta=(
            cuenta.limite_credito_cuenta
        ),
        credito_utilizado_cuenta=(
            credito_utilizado
        ),
        saldo_disponible_credito_cuenta=(
            saldo_disponible
        ),
        porcentaje_utilizacion_credito_cuenta=(
            porcentaje
        ),
    )


def registrar_cuenta(
    db: Session,
    usuario: Usuario,
    datos: CuentaCrearEntrada,
) -> CuentaPublica:

    nombre = datos.nombre_cuenta.strip()

    cuenta_existente = (
        repository.obtener_por_nombre(
            db,
            usuario.id_usuario,
            nombre,
        )
    )

    if cuenta_existente is not None:
        raise NombreCuentaDuplicadoError()

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

    cuenta = Cuenta(
        usuario_id=usuario.id_usuario,
        nombre_cuenta=nombre,
        tipo_cuenta=datos.tipo_cuenta,
        institucion_cuenta=institucion,
        numero_cuenta=numero,
        saldo_inicial_cuenta=(
            datos.saldo_inicial_cuenta
        ),
        limite_credito_cuenta=(
            datos.limite_credito_cuenta
        ),
    )

    try:
        cuenta = repository.crear(
            db,
            cuenta,
        )

    except IntegrityError:
        raise NombreCuentaDuplicadoError()

    return construir_cuenta_publica(
        cuenta
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

    items = [
        CuentaListaItem(
            id_cuenta=cuenta.id_cuenta,
            nombre_cuenta=cuenta.nombre_cuenta,
            tipo_cuenta=cuenta.tipo_cuenta,
            institucion_cuenta=(
                cuenta.institucion_cuenta
            ),
            numero_cuenta_enmascarado=(
                enmascarar_numero_cuenta(
                    cuenta.numero_cuenta
                )
            ),
            es_activa_cuenta=(
                cuenta.es_activa_cuenta
            ),
            saldo_actual_cuenta=(
                calcular_saldo_actual(
                    cuenta
                )
            ),
        )
        for cuenta in cuentas
    ]

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

    return construir_cuenta_publica(
        cuenta
    )


def actualizar_cuenta(
    db: Session,
    usuario: Usuario,
    id_cuenta,
    datos: CuentaActualizarEntrada,
) -> CuentaPublica:

    cuenta = repository.obtener_por_id(
        db,
        id_cuenta,
        usuario.id_usuario,
    )

    if cuenta is None:
        raise CuentaNoEncontradaError()

    cambios = datos.model_dump(
        exclude_unset=True
    )

    if "nombre_cuenta" in cambios:

        nombre = cambios[
            "nombre_cuenta"
        ].strip()

        otra = repository.obtener_por_nombre(
            db,
            usuario.id_usuario,
            nombre,
        )

        if (
            otra is not None
            and otra.id_cuenta != cuenta.id_cuenta
        ):
            raise NombreCuentaDuplicadoError()

        cambios["nombre_cuenta"] = nombre

    if "institucion_cuenta" in cambios:
        cambios["institucion_cuenta"] = (
            normalizar_texto(
                cambios["institucion_cuenta"]
            )
        )

    if "numero_cuenta" in cambios:
        cambios["numero_cuenta"] = (
            normalizar_numero_cuenta(
                cambios["numero_cuenta"]
            )
        )

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

    if (
        cuenta.tipo_cuenta
        == TipoCuenta.CREDITO
        and "limite_credito_cuenta" in cambios
    ):
        credito_utilizado = (
            calcular_credito_utilizado(cuenta)
        )

        if nuevo_limite < credito_utilizado:
            raise LimiteCreditoInvalidoError()

    try:
        cuenta = repository.actualizar(
            db,
            cuenta,
            cambios,
        )

    except IntegrityError:
        raise NombreCuentaDuplicadoError()

    return construir_cuenta_publica(
        cuenta
    )


def cambiar_estado_cuenta(
    db: Session,
    usuario: Usuario,
    id_cuenta,
    es_activa: bool,
) -> CuentaEstadoSalida:

    cuenta = repository.obtener_por_id(
        db,
        id_cuenta,
        usuario.id_usuario,
    )

    if cuenta is None:
        raise CuentaNoEncontradaError()

    cuenta = repository.cambiar_estado(
        db,
        cuenta,
        es_activa,
    )

    return CuentaEstadoSalida(
        id_cuenta=cuenta.id_cuenta,
        es_activa_cuenta=(
            cuenta.es_activa_cuenta
        ),
    )