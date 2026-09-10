from fastapi import FastAPI

from app.modules.usuarios.auth_router import router as auth_router
from app.modules.usuarios.router import router as usuarios_router
from app.modules.cuentas.router import router as cuentas_router


app = FastAPI(
    title="FinTrack API",
    description="API backend para la aplicación FinTrack",
    version="1.0.0",
)

app.include_router(
    auth_router,
    prefix="/api/v1",
)

app.include_router(
    usuarios_router,
    prefix="/api/v1",
)

app.include_router(
    cuentas_router,
    prefix="/api/v1",
)


@app.get("/", tags=["Sistema"])
def health_check():
    return {
        "status": "ok",
        "message": "FinTrack API Online",
    }