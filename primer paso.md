# Primer paso — levantar el proyecto en local con Docker

Sesión del 2026-11-09. Registro de lo que se hizo para que la próxima sesión sepa el estado.

## Qué se hizo

1. **Docker Desktop estaba apagado** → se inició (`C:\Program Files\Docker\Docker\Docker Desktop.exe`).
   Al recién arrancar, la API de Docker puede devolver `500 Internal Server Error` unos segundos: hay que esperar y reintentar.
2. **Se creó `.env` en la raíz** a partir de `.env.produccion.example`, con:
   - `DOMINIO=localhost`
   - `POSTGRES_PASSWORD` y `SECRET_KEY` aleatorias (generadas con `secrets` de Python).
   - `OPENAI_API_KEY` **quedó con el valor de ejemplo** → voz (CU11), foto (CU12) y asistente (CU13) no funcionan hasta poner una key real.
   - El `.env` está en `.gitignore` (verificado), no se sube a git.
3. **Se levantó todo**: `docker compose up --build -d` → contenedores `db`, `backend`, `web` corriendo
   (el backend aplica `alembic upgrade head` solo al arrancar).
4. **Se creó el usuario de prueba**: `docker compose exec backend python -m app.seed`
   → `admin@diagramador.com` / `admin12345`.

## Verificación hecha

- `https://localhost/api/health/db` → `{"database":"conectada correctamente"}`
- `POST https://localhost/api/auth/login` con el admin → devuelve token.
- `https://localhost/` → 200 (frontend cargando).

## Cómo usarlo

- Abrir **https://localhost** (aceptar el aviso de certificado: Avanzado → Continuar; es un certificado local de Caddy).
- Comandos desde la raíz del proyecto:

```powershell
docker compose up -d                 # encender (Docker Desktop debe estar abierto)
docker compose down                  # apagar (los datos se conservan)
docker compose down -v               # apagar y BORRAR la base de datos
docker compose logs -f backend       # ver logs del backend
docker compose up --build -d         # reconstruir tras cambiar código
docker compose up -d backend         # reiniciar backend tras editar .env
```

## Pendiente

- Poner una `OPENAI_API_KEY` real en `.env` (raíz) y correr `docker compose up -d backend` para habilitar voz/foto/asistente.
- Para desarrollar con recarga automática conviene el modo manual (`uvicorn --reload` + `npm run dev`, ver `CLAUDE.md` → Comandos);
  para eso falta crear `backend/venv`, `backend/.env` (desde `backend/.env.example`) y tener PostgreSQL local — no se hizo en esta sesión.
