
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "No se encontró DATABASE_URL en las variables de entorno."
    )

# Usar psycopg 3 con SQLAlchemy
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


def mostrar_resultados(titulo, filas):
    print(f"\n{'=' * 65}")
    print(titulo)
    print("=" * 65)

    if not filas:
        print("No se encontraron resultados.")
        return

    for fila in filas:
        print(dict(fila))


def ejecutar_consulta(conexion, titulo, sql):
    filas = conexion.execute(text(sql)).mappings().all()
    mostrar_resultados(titulo, filas)


def verificar_neon():
    try:
        with engine.connect() as conexion:

            ejecutar_consulta(
                conexion,
                "1. COLUMNAS DE META Y ASIGNACION_META",
                """
                SELECT
                    table_name,
                    column_name,
                    data_type,
                    udt_name,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'meta',
                      'asignacion_meta'
                  )
                ORDER BY table_name, ordinal_position
                """
            )

            ejecutar_consulta(
                conexion,
                "2. RESTRICCIONES DE LAS TABLAS",
                """
                SELECT
                    c.conrelid::regclass::text AS tabla,
                    c.conname AS restriccion,
                    c.contype AS tipo,
                    pg_get_constraintdef(c.oid) AS definicion
                FROM pg_constraint c
                WHERE c.conrelid IN (
                    to_regclass('public.meta'),
                    to_regclass('public.asignacion_meta')
                )
                ORDER BY tabla, restriccion
                """
            )

            ejecutar_consulta(
                conexion,
                "3. INDICES",
                """
                SELECT
                    tablename,
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN (
                      'meta',
                      'asignacion_meta'
                  )
                ORDER BY tablename, indexname
                """
            )

            ejecutar_consulta(
                conexion,
                "4. VISTAS FINANCIERAS V1.1",
                """
                SELECT
                    table_name AS vista
                FROM information_schema.views
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'vw_meta_resumen_v11',
                      'vw_reserva_meta_cuenta_v11',
                      'vw_estado_financiero_cuenta'
                  )
                ORDER BY table_name
                """
            )

            ejecutar_consulta(
                conexion,
                "5. COLUMNAS DE LAS VISTAS V1.1",
                """
                SELECT
                    table_name AS vista,
                    column_name,
                    data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'vw_meta_resumen_v11',
                      'vw_reserva_meta_cuenta_v11'
                  )
                ORDER BY table_name, ordinal_position
                """
            )

            ejecutar_consulta(
                conexion,
                "6. CANTIDAD DE METAS Y ASIGNACIONES",
                """
                SELECT
                    'meta' AS tabla,
                    (SELECT COUNT(*) FROM public.meta) AS registros
                UNION ALL
                SELECT
                    'asignacion_meta',
                    (SELECT COUNT(*) FROM public.asignacion_meta)
                """
            )

            print("\nVerificación finalizada correctamente.")

    except Exception as error:
        print("\nError al verificar Neon:")
        print(f"{type(error).__name__}: {error}")

    finally:
        engine.dispose()


if __name__ == "__main__":
    verificar_neon()
