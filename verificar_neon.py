from sqlalchemy import create_engine, text
from app.core.config import settings

OBJETOS = {
    "fintrack_schema_version": "r",
    "prediccion": "r",
    "vw_movimiento_analitico_v11": "v",
    "vw_transaccion_periodo_v11": "v",
    "vw_periodo_resumen_v11": "v",
    "vw_detalle_periodo_grupo_v11": "v",
}

def verificar():
    engine = create_engine(settings.DATABASE_URL)

    try:
        with engine.connect() as conexion:
            print("\n=== VERIFICACIÓN SOFT COMPUTING V1.1 ===\n")

            for nombre, tipo_esperado in OBJETOS.items():
                resultado = conexion.execute(
                    text("""
                        SELECT c.relkind
                        FROM pg_catalog.pg_class c
                        JOIN pg_catalog.pg_namespace n
                          ON n.oid = c.relnamespace
                        WHERE n.nspname = 'public'
                          AND c.relname = :nombre
                    """),
                    {"nombre": nombre},
                ).scalar_one_or_none()

                # r = tabla ordinaria; v = vista; m = vista materializada.
                correcto = resultado == tipo_esperado

                print(
                    f"{'[OK]' if correcto else '[FALTA O TIPO DISTINTO]'} "
                    f"{nombre}"
                )

            funcion = conexion.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_proc p
                        JOIN pg_catalog.pg_namespace n
                          ON n.oid = p.pronamespace
                        WHERE n.nspname = 'public'
                          AND p.proname = 'fn_usuario_lock_v11'
                    )
                """)
            ).scalar()

            print(
                f"{'[OK]' if funcion else '[FALTA]'} "
                "fn_usuario_lock_v11"
            )

            tabla_version = conexion.execute(
                text("""
                    SELECT to_regclass(
                        'public.fintrack_schema_version'
                    )
                """)
            ).scalar()

            if tabla_version is not None:
                version = conexion.execute(
                    text("""
                        SELECT version
                        FROM public.fintrack_schema_version
                        ORDER BY aplicado_en DESC
                        LIMIT 1
                    """)
                ).scalar_one_or_none()

                print(f"\nVersión del esquema: {version}")

    except Exception as error:
        print(f"\nError de verificación: {type(error).__name__}")
        print("Revisa la conexión, los permisos o el esquema.")

    finally:
        engine.dispose()


if __name__ == "__main__":
    verificar()