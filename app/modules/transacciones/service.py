from uuid import UUID

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.modules.transacciones import repository
from app.modules.transacciones.model import TipoTransaccion, Transaccion
from app.modules.transacciones.schemas import TransaccionCrearEntrada


class TransaccionNoEncontradaError(Exception):
    pass


class CuentaNoEncontradaError(Exception):
    pass


class ReglaTransaccionError(Exception):
    def __init__(self, codigo: str, status_code: int = 409):
        self.codigo = codigo
        self.status_code = status_code
        super().__init__(codigo)


# Mensajes explícitos de las funciones verificadas en Neon V1.1.
ERRORES_BD = {
    "CUENTA_NO_ENCONTRADA": (404, "CUENTA_NO_ENCONTRADA"),
    "CUENTA_DESTINO_NO_ENCONTRADA": (404, "CUENTA_NO_ENCONTRADA"),
    "CUENTA_INACTIVA": (409, "CUENTA_INACTIVA"),
    "CUENTAS_IGUALES": (422, "CUENTAS_IGUALES"),
    "MONTO_INVALIDO": (422, "MONTO_INVALIDO"),
    "ENTRADA_LIQUIDA_NO_ADMITE_CREDITO": (422, "ENTRADA_LIQUIDA_NO_ADMITE_CREDITO"),
    "AHORRO_NO_ADMITE_COMPRA_DIRECTA": (422, "AHORRO_NO_ADMITE_COMPRA_DIRECTA"),
    "CREDITO_NO_PUEDE_ORIGINAR_TRANSFERENCIA_O_PAGO": (422, "CREDITO_NO_PUEDE_ORIGINAR_TRANSFERENCIA_O_PAGO"),
    "EL_PASIVO_VINCULADO_DEBE_SER_CREDITO_PROPIO": (422, "EL_PASIVO_VINCULADO_DEBE_SER_CREDITO_PROPIO"),
    "CATEGORIA_NO_ELEGIBLE": (409, "CATEGORIA_NO_ELEGIBLE"),
    "SUBCATEGORIA_NO_ELEGIBLE": (409, "SUBCATEGORIA_NO_ELEGIBLE"),
    "DINERO_LIBRE_INSUFICIENTE": (409, "DINERO_LIBRE_INSUFICIENTE"),
    "LIMITE_CREDITO_EXCEDIDO": (409, "LIMITE_CREDITO_EXCEDIDO"),
    "DEVOLUCION_SUPERA_DEUDA": (409, "DEVOLUCION_SUPERA_DEUDA"),
    "PAGO_SUPERA_DEUDA": (409, "PAGO_SUPERA_DEUDA"),
    "FECHA_OPERACION_FUTURA_O_INVALIDA": (422, "FECHA_OPERACION_FUTURA_O_INVALIDA"),
    "FECHA_FUERA_DEL_PERIODO_ACTIVO": (409, "FECHA_FUERA_DEL_PERIODO_ACTIVO"),
    "USUARIO_NO_ENCONTRADO": (403, "USUARIO_NO_DISPONIBLE"),
    "USUARIO_DESACTIVADO": (403, "USUARIO_DESACTIVADO"),
    "AISLAMIENTO_NO_ADMITIDO": (500, "AISLAMIENTO_NO_ADMITIDO"),
}


def traducir_error_bd(exc: DBAPIError) -> ReglaTransaccionError | None:
    original = getattr(exc, "orig", None)
    diag = getattr(original, "diag", None)
    mensaje = getattr(diag, "message_primary", None) or str(original or "")
    for clave, (estado, codigo) in ERRORES_BD.items():
        if mensaje.startswith(clave):
            return ReglaTransaccionError(codigo, estado)
    # Una restricción de estructura o referencia puede fallar antes/después del trigger.
    codigo_sql = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
    if codigo_sql in {"23514", "23502", "22P02"}:
        return ReglaTransaccionError("ESTRUCTURA_TRANSACCION_INVALIDA", 422)
    if codigo_sql == "23503":
        return ReglaTransaccionError("REFERENCIA_TRANSACCION_INVALIDA", 422)
    return None


def crear_transaccion(db: Session, usuario_id: UUID, datos: TransaccionCrearEntrada) -> Transaccion:
    try:
        repository.bloquear_usuario(db, usuario_id)
        ids = [datos.cuenta_id]
        if datos.cuenta_destino_id is not None:
            ids.append(datos.cuenta_destino_id)
        cuentas = repository.bloquear_cuentas(db, usuario_id, ids)
        if len(cuentas) != len(set(ids)):
            raise CuentaNoEncontradaError()
        # No calcular saldos ni fondos: fn_transaccion_validar_v11 usa la vista oficial.
        # No enviar periodo_id, grupo_id, es_ingreso_reservado ni id_transaccion:
        # el trigger fija esos valores de forma autoritativa.
        transaccion = Transaccion(
            usuario_id=usuario_id,
            cuenta_id=datos.cuenta_id,
            cuenta_destino_id=datos.cuenta_destino_id,
            tipo_transaccion=datos.tipo_transaccion,
            categoria_id=datos.categoria_id,
            subcategoria_id=datos.subcategoria_id,
            monto_transaccion=datos.monto_transaccion,
            monto_reduccion_deuda=datos.monto_reduccion_deuda,
            fecha_operacion_transaccion=datos.fecha_operacion_transaccion,
            comentario_transaccion=datos.comentario_transaccion,
            referencia_transaccion=datos.referencia_transaccion,
        )
        repository.agregar_transaccion(db, transaccion)
        db.commit()
        db.refresh(transaccion)
        return transaccion
    except (IntegrityError, DBAPIError) as exc:
        db.rollback()
        traducido = traducir_error_bd(exc)
        if traducido is not None:
            raise traducido from exc
        raise
    except Exception:
        db.rollback()
        raise


def obtener_transaccion(db: Session, usuario_id: UUID, id_transaccion: UUID) -> Transaccion:
    transaccion = repository.obtener_transaccion_por_id(db, usuario_id, id_transaccion)
    if transaccion is None:
        raise TransaccionNoEncontradaError()
    return transaccion


def listar_transacciones(
    db: Session,
    usuario_id: UUID,
    tipo_transaccion: TipoTransaccion | None,
    cuenta_id: UUID | None,
    limite: int,
    offset: int,
) -> tuple[list[Transaccion], int]:
    if cuenta_id is not None and repository.obtener_cuenta_propia(db, usuario_id, cuenta_id) is None:
        raise CuentaNoEncontradaError()
    return repository.listar_transacciones(db, usuario_id, tipo_transaccion, cuenta_id, limite, offset)
