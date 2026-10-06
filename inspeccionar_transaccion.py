from app.db.session import engine

with engine.connect() as conn:
    resultado = conn.exec_driver_sql("""
        SELECT
            t.typname AS enum_name,
            e.enumlabel AS enum_value
        FROM pg_type t
        JOIN pg_enum e
            ON t.oid = e.enumtypid
        WHERE t.typname = 'estado_presupuesto_enum'
        ORDER BY e.enumsortorder
    """)

    for fila in resultado:
        print(fila)