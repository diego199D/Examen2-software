# Backend del Diagramador UML (FastAPI) para producción.
# Ver DESPLIEGUE.md en la raíz del repo.

# Misma versión de Python que se usa en desarrollo (3.14).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
# Incluye app/services/plantillas_android/ (binarios que usa la generación
# Flutter, CU15) -- tienen que estar commiteados en el repo.
COPY app ./app
COPY docker-entrypoint.sh .

# sed: por si el script llegó con fin de línea de Windows (ver .gitattributes).
RUN useradd --create-home --uid 1000 diagramador \
    && sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod +x docker-entrypoint.sh \
    && chown -R diagramador:diagramador /app
USER diagramador

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
