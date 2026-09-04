from sqlalchemy import text

from app.db.session import engine


sql = text("""
    SELECT
        column_name,
        data_type,
        character_maximum_length,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_name = 'usuario'
      AND table_schema = 'public'
    ORDER BY ordinal_position;
""")


with engine.connect() as connection:
    resultado = connection.execute(sql)

    for fila in resultado:
        print(fila)