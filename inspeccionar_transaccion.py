from sqlalchemy import text

from app.db.session import engine


TABLAS = [
    "transaccion",
    "categoria",
    "subcategoria",
]


sql_columnas = text("""
    SELECT
        column_name,
        data_type,
        udt_name,
        character_maximum_length,
        numeric_precision,
        numeric_scale,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_name = :tabla
      AND table_schema = 'public'
    ORDER BY ordinal_position;
""")


sql_constraints = text("""
    SELECT
        con.conname AS nombre,
        con.contype AS tipo,
        pg_get_constraintdef(con.oid) AS definicion
    FROM pg_constraint con
    JOIN pg_class rel
        ON rel.oid = con.conrelid
    JOIN pg_namespace nsp
        ON nsp.oid = rel.relnamespace
    WHERE rel.relname = :tabla
      AND nsp.nspname = 'public'
    ORDER BY con.conname;
""")


sql_indices = text("""
    SELECT
        indexname,
        indexdef
    FROM pg_indexes
    WHERE tablename = :tabla
      AND schemaname = 'public'
    ORDER BY indexname;
""")


with engine.connect() as connection:

    for tabla in TABLAS:

        print("\n")
        print("=" * 70)
        print(f"TABLA: {tabla.upper()}")
        print("=" * 70)

        print("\n=== COLUMNAS ===")

        columnas = connection.execute(
            sql_columnas,
            {"tabla": tabla},
        )

        for fila in columnas:
            print(fila)

        print("\n=== RESTRICCIONES ===")

        restricciones = connection.execute(
            sql_constraints,
            {"tabla": tabla},
        )

        for fila in restricciones:
            print(fila)

        print("\n=== ÍNDICES ===")

        indices = connection.execute(
            sql_indices,
            {"tabla": tabla},
        )

        for fila in indices:
            print(fila)
sql_enums = text("""
    SELECT
        t.typname AS enum_name,
        e.enumlabel AS enum_value
    FROM pg_type t
    JOIN pg_enum e
        ON t.oid = e.enumtypid
    JOIN pg_namespace n
        ON n.oid = t.typnamespace
    WHERE n.nspname = 'public'
    ORDER BY
        t.typname,
        e.enumsortorder;
""")


with engine.connect() as connection:

    print("\n=== ENUMS DE POSTGRESQL ===")

    resultado = connection.execute(sql_enums)

    for fila in resultado:
        print(fila)