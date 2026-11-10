#!/bin/sh
# Arranque del backend en producción: aplica las migraciones pendientes y
# levanta la API.
set -e

alembic upgrade head

# --workers 1 A PROPÓSITO, no subirlo: las salas de colaboración en tiempo
# real (CU10, app/services/yjs_rooms.py) viven en la memoria del proceso.
# Con 2 o más workers (o 2 contenedores del backend), dos usuarios del mismo
# proyecto podrían caer en procesos distintos y dejarían de verse los
# cambios entre sí.
# --proxy-headers: el backend está detrás de Caddy (HTTPS termina ahí).
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips="*"
