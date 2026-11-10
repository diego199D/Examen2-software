# Despliegue en AWS (una EC2 con Docker)

Guía paso a paso para poner en línea el Diagramador UML en una sola
instancia EC2, con todo funcionando igual que en local: editor, colaboración
en tiempo real, comandos de voz, reconocimiento por foto, asistente,
generación de backend/frontend, reportes e importación XMI.

## Cómo queda armado

```
Internet ──443/80──> [ web: Caddy ] ──/api/*──> [ backend: FastAPI ] ──> [ db: PostgreSQL ]
                        └── el resto: la página (frontend compilado)
```

Tres contenedores definidos en `docker-compose.yml`:

| Contenedor | Qué hace |
|---|---|
| `web` | Caddy: sirve el frontend, pasa `/api/*` al backend y saca solo el certificado HTTPS (Let's Encrypt). Es el único que expone puertos (80 y 443). |
| `backend` | FastAPI. Al arrancar aplica las migraciones (`alembic upgrade head`). |
| `db` | PostgreSQL 17. Los datos viven en un volumen de Docker (`pgdata`), no se pierden al reiniciar. No es accesible desde internet. |

### Tres reglas que no hay que romper

1. **HTTPS obligatorio.** Los comandos de voz usan el micrófono del
   navegador, y el navegador solo lo permite en páginas `https://`. Por eso
   se entra siempre por el nombre `https://<ip-con-guiones>.sslip.io`, nunca
   por `http://` ni por la IP sola.
2. **Un solo backend.** Las salas de colaboración en tiempo real viven en la
   memoria del backend. No subir los workers de uvicorn ni levantar dos
   contenedores `backend`: los usuarios de un mismo proyecto dejarían de
   verse entre sí.
3. **La API va bajo `/api`.** El frontend la busca ahí solo, en el mismo
   dominio desde el que se abrió la página. No hace falta configurar la URL.

### ¿Por qué sslip.io?

Sin dominio propio no se puede sacar un certificado HTTPS para una IP sola.
[sslip.io](https://sslip.io) es un servicio gratuito, sin registro, que
convierte la IP en un nombre: `54-12-3-4.sslip.io` apunta a `54.12.3.4`.
Con ese nombre Caddy consigue un certificado real de Let's Encrypt. Si más
adelante se compra un dominio, solo cambia `DOMINIO` en el `.env`.

---

## Paso 0 — Antes de empezar (en tu PC)

El servidor va a clonar el repositorio, así que **todo tiene que estar
commiteado y subido a GitHub**. En especial:

- `backend/app/services/plantillas_android/` (el `gradle-wrapper.jar` y los
  íconos): sin estos archivos la generación de la app Flutter falla.
- Todos los cambios pendientes (`git status` tiene que quedar limpio).

```bash
git status
git add -A
git commit -m "Preparar despliegue"
git push
```

Verificá en GitHub que exista `backend/app/services/plantillas_android/gradle-wrapper.jar`.

Si el repositorio es **privado**, vas a necesitar un token de GitHub para
clonarlo en el servidor (Paso 4).

## Paso 1 — Crear la instancia EC2

En la consola de AWS → EC2 → *Launch instance*:

| Opción | Valor |
|---|---|
| Nombre | `diagramador-uml` |
| Imagen (AMI) | **Ubuntu Server 24.04 LTS** |
| Tipo | **t3.small** (2 GB de RAM). Con t3.micro (1 GB) la compilación del frontend puede quedarse sin memoria — si igual la usás, hacé el paso de *swap* de abajo. |
| Par de claves | Crear uno nuevo (`.pem`) y guardarlo: es la llave para entrar por SSH. |
| Almacenamiento | 20 GB (gp3) |

**Security Group** (reglas de entrada):

| Puerto | Origen | Para qué |
|---|---|---|
| 22 (SSH) | *Mi IP* | Entrar a administrar el servidor |
| 80 (HTTP) | 0.0.0.0/0 | Let's Encrypt valida el certificado por acá; Caddy además redirige a HTTPS |
| 443 (HTTPS) | 0.0.0.0/0 | El sitio |

## Paso 2 — IP fija (Elastic IP)

La IP pública de una EC2 **cambia cada vez que se detiene y arranca**, y con
ella cambiaría el nombre sslip.io (y el certificado). Para evitarlo:

EC2 → *Elastic IPs* → *Allocate Elastic IP address* → *Associate* con la
instancia `diagramador-uml`.

Anotá esa IP. Ejemplo: `54.12.3.4` → tu dominio será `54-12-3-4.sslip.io`.

> Una Elastic IP asociada a una instancia encendida no tiene costo extra;
> si la instancia está apagada o la IP queda sin asociar, AWS la cobra.

## Paso 3 — Entrar al servidor e instalar Docker

Desde tu PC (PowerShell), en la carpeta donde está el `.pem`:

```bash
ssh -i diagramador.pem ubuntu@54.12.3.4
```

Ya dentro del servidor:

```bash
# Docker (script oficial) + permisos para usarlo sin sudo
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

Volvé a entrar por SSH (para que tome el permiso) y verificá:

```bash
docker --version
docker compose version
```

**Solo si usaste t3.micro** — agregar 2 GB de swap:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Paso 4 — Clonar el proyecto y configurarlo

```bash
git clone https://github.com/<usuario>/<repo>.git diagramador-uml
cd diagramador-uml
cp .env.produccion.example .env
nano .env
```

Completá cada valor (el archivo explica cada uno):

- `DOMINIO` → tu IP con guiones + `.sslip.io` (ej. `54-12-3-4.sslip.io`).
- `POSTGRES_PASSWORD` y `SECRET_KEY` → generalos así y pegá el resultado:
  ```bash
  openssl rand -hex 24      # para POSTGRES_PASSWORD
  openssl rand -base64 48   # para SECRET_KEY
  ```
- `OPENAI_API_KEY` → la misma key que usás en local (o una nueva).

Guardá con `Ctrl+O`, `Enter`, `Ctrl+X`.

## Paso 5 — Levantar todo

```bash
docker compose up -d --build
```

La primera vez tarda varios minutos (descarga imágenes, instala
dependencias, compila el frontend). Para ver cómo va:

```bash
docker compose ps              # los 3 tienen que estar "running" (db "healthy")
docker compose logs -f web     # esperar "certificate obtained successfully"
```

`Ctrl+C` sale de los logs sin apagar nada.

## Paso 6 — Crear tu usuario

Entrá a `https://54-12-3-4.sslip.io/registro` y creá tu cuenta (el registro
crea usuarios administradores).

> Existe también `docker compose exec backend python -m app.seed`, que crea
> `admin@diagramador.com` / `admin12345`. **En un servidor público no lo
> uses** (o cambiá esa contraseña enseguida desde *Perfil*): es una
> contraseña conocida.

## Paso 7 — Verificar que todo funciona

Abrí `https://<tu-dominio>` y revisá:

- [ ] El navegador muestra el **candado** (HTTPS válido, sin advertencias).
- [ ] Login y lista de proyectos.
- [ ] Crear un proyecto, agregar clases y relaciones; recargar y que sigan ahí.
- [ ] **Colaboración:** abrir el mismo proyecto en otro navegador (o
      ventana de incógnito) con otro usuario agregado como colaborador: los
      cambios y el cursor se ven en tiempo real, y el indicador "En vivo" está verde.
- [ ] **Voz:** el botón del micrófono pide permiso y un comando ("crear clase Persona") funciona.
- [ ] **Foto:** "Reconocer por foto" con una imagen de un diagrama.
- [ ] **Asistente** responde.
- [ ] **Generar backend** y **generar frontend** descargan el `.zip`.
- [ ] **Exportar** PDF, Imagen y XMI.
- [ ] **Importar XMI** en un proyecto vacío.

---

## Operación del día a día

**Ver logs**

```bash
docker compose logs -f backend      # o web / db
```

**Actualizar después de un cambio en el código** (después de `git push` desde tu PC):

```bash
cd ~/diagramador-uml
git pull
docker compose up -d --build
```

Las migraciones nuevas se aplican solas al arrancar el backend. Durante el
reinicio (unos segundos) los usuarios conectados se desconectan y
reconectan solos.

**Backup de la base de datos**

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup-$(date +%F).sql
```

Para bajarlo a tu PC (desde PowerShell en tu PC):

```bash
scp -i diagramador.pem ubuntu@54.12.3.4:~/diagramador-uml/backup-AAAA-MM-DD.sql .
```

**Restaurar un backup** (reemplaza los datos actuales):

```bash
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup-AAAA-MM-DD.sql
```

**Apagar / encender**

```bash
docker compose down     # apaga (los datos quedan en el volumen)
docker compose up -d    # enciende
```

> `docker compose down -v` **borra también la base de datos** y los
> certificados. No usarlo en producción salvo que sea a propósito.

**Si cambia la IP** (por ejemplo, no se usó Elastic IP): editar `DOMINIO`
en `.env` con la IP nueva y `docker compose up -d`. Caddy saca un
certificado nuevo solo.

**Pasar a RDS más adelante** (opcional): crear la base en RDS PostgreSQL,
cambiar `DATABASE_URL` del servicio `backend` en `docker-compose.yml` para
que apunte a RDS y quitar el servicio `db`.

---

## Problemas comunes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El sitio no carga / el certificado no sale (`docker compose logs web` muestra errores de "challenge") | Puertos 80 o 443 cerrados en el Security Group, o `DOMINIO` mal escrito | Revisar el Security Group (Paso 1) y que `DOMINIO` sea la IP elástica con guiones + `.sslip.io` |
| "too many certificates" en los logs de `web` | Se pidieron muchos certificados en poco tiempo (p. ej. borrando el volumen `caddy_data`) | Esperar (el límite es semanal) y no borrar `caddy_data` |
| El micrófono no aparece o da error de permisos | Se entró por `http://` o por la IP sola | Entrar siempre por `https://<ip-con-guiones>.sslip.io` |
| Voz, foto o asistente responden "servicio no disponible" | Falta o está mal `OPENAI_API_KEY`, o la cuenta de OpenAI no tiene saldo | Revisar `.env` y `docker compose up -d` |
| El indicador de colaboración queda gris/rojo | El WebSocket no conecta | `docker compose logs backend`; verificar que se entra por HTTPS |
| La compilación se corta con "Killed" | Poca memoria (t3.micro) | Agregar swap (Paso 3) |
| "Generar frontend" falla | Faltan `plantillas_android/` en el repo | Paso 0: commitearlas, `git pull` y `docker compose up -d --build` |
| `backend` se reinicia en loop | Error de conexión a la base o migración fallida | `docker compose logs backend` |
