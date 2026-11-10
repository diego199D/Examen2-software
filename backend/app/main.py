from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.routers import (
    agente,
    auth,
    colaboradores,
    comandos_voz,
    diagramas,
    generacion,
    proyectos,
    reconocimiento_foto,
    reportes,
    usuarios,
    ws_diagramas,
)

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Sin esto el navegador oculta Content-Disposition a JS (no está en la
    # lista de headers "seguros" por defecto de CORS) — lo necesitan
    # generacion.py (CU08, .zip) y reportes.py (CU07, .pdf) para nombrar el
    # archivo descargado.
    expose_headers=["Content-Disposition"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(proyectos.router)
app.include_router(colaboradores.router)
app.include_router(diagramas.router)
app.include_router(ws_diagramas.router)
app.include_router(generacion.router)
app.include_router(reportes.router)
app.include_router(comandos_voz.router)
app.include_router(agente.router)
app.include_router(reconocimiento_foto.router)


@app.get("/")
def root():
    return {"message": f"{settings.PROJECT_NAME} API activa"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "conectada correctamente"}
