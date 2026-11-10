# Frontend del Diagramador UML para producción: compila la SPA con Vite y la
# sirve con Caddy, que además hace de proxy hacia el backend (/api) y saca el
# certificado HTTPS solo. Ver DESPLIEGUE.md en la raíz del repo.

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Sin VITE_API_URL a propósito: en producción el frontend usa
# `${window.location.origin}/api` (ver src/api/client.ts), así la misma
# imagen sirve para cualquier IP o dominio.
RUN npm run build

FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
