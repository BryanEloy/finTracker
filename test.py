from sqlalchemy import create_engine


engine=create_engine(

"postgresql://postgres:Dinerofacil.1@localhost:5432/testdb"

)


conn=engine.connect()

print("Conectado")

conn.close()