# Decisiones del segundo parcial

Cuando la consigna era ambigua (o la especificación del docente no estaba en el repo), se eligió la opción más razonable y se documenta acá.

## 0. Contexto

- La especificación del docente (`docs/especificacion-parcial2.md`) **no estaba en el repositorio** cuando se hizo este trabajo. Las referencias a §6.1–§6.4 y a los escenarios §7 se resolvieron con lo que dice el prompt de trabajo. El esquema de eventos y la herramienta `apply_diagram_mutations` están definidos acá (secciones 3 y 4) y en `docs/documentacion-tecnica.md`.
- El nombre del grupo **no es fijo en el código** (y la documentación no lista integrantes). Cada usuario se registra con su nombre y el nombre de su grupo, y la interfaz muestra siempre el grupo de quien está logueado.

## 1. IA: Google Gemini

- SDK oficial `google-genai` (Python), centralizado en `backend/app/services/ai/gemini_client.py`. Es el único módulo que importa el SDK.
- Modelo por defecto: `gemini-3.5-flash`, tanto para texto como para visión. Se verificó contra la API real con la key del proyecto: `gemini-2.5-flash` ya no está disponible para cuentas nuevas y `gemini-3.8-flash` respondía 503 por saturación. Respaldo: `gemini-3.1-flash-lite` (`GEMINI_FALLBACK_MODEL`).
- Los esquemas de herramientas se escriben como JSON Schema y `esquema_gemini()` los traduce al subconjunto OpenAPI de Gemini:
  - `type: [X, "null"]` pasa a `nullable`;
  - se quitan `additionalProperties` y `strict`;
  - se rechazan `oneOf`, `$ref` y los objetos sin `properties`;
  - se conserva el orden de las propiedades. Importa: en CU12 cada multiplicidad va junto a su clase.
- Errores 429/5xx: hasta 3 reintentos con backoff exponencial y, si siguen, el modelo de respaldo. Después de eso, un mensaje claro para el usuario ("límite de uso… espera unos segundos").
- No hay `transcribe_audio`: la voz se reconoce en el navegador (Web Speech API) y al backend solo llega texto.

## 2. Relaciones y generador de backend

Un único modelo relacional intermedio (`backend/app/services/modelo_relacional.py`) alimenta el generador Spring, el DDL exportado, la colección Postman y la app Flutter. Así las columnas, el JSON y las rutas nunca se desincronizan.

| Caso | Mapeo |
|---|---|
| Multiplicidad plural | `*`, `0..*`, `1..*` (`*` se agregó en este parcial) |
| 1:1 | FK `UNIQUE` en el origen. En composición o agregación va en la parte (destino), para que `ON DELETE` tenga sentido |
| 1:N | FK en el lado N |
| N:M | Tabla intermedia `tablaA_tablaB` (tablas en orden alfabético) o el nombre que elija el usuario (`Relacion.tabla_intermedia`). PK compuesta, FKs `ON DELETE CASCADE`, índice en la segunda columna. JPA: `@ManyToMany` + `Set` |
| Clase de asociación | Campo opcional `Relacion.id_clase_asociacion`. La tabla de esa clase **es** la intermedia: PK propia, `UNIQUE(a_id, b_id)` y dos FKs `NOT NULL ON DELETE CASCADE`. Se eligió así, en vez de exigir modelar a mano dos 1:N, porque en el lienzo se dibuja con la notación UML estándar: una línea punteada desde la clase hasta la relación |
| Herencia | Tabla por subclase (JPA `JOINED`): la tabla hija tiene `id` como PK y FK a la padre (`ON DELETE CASCADE`). Si hay herencia múltiple se toma el primer padre; los ciclos se ignoran (queda un aviso en el DDL) |
| Composición | `ON DELETE CASCADE`, más `cascade=ALL, orphanRemoval` en JPA |
| Agregación | `ON DELETE SET NULL`. La FK siempre admite NULL, porque la parte existe sin el todo |
| Asociación | `ON DELETE RESTRICT`. Borrar algo referenciado da 409 |
| NOT NULL | Cuando la multiplicidad del extremo referenciado es exactamente `1` |

Otras decisiones del generador:

- **Clase abstracta**: es `abstract` en Java y su controlador no tiene POST ni PUT.
- **Esquema**: lo crea una migración Flyway (`V1__esquema_inicial.sql`), no Hibernate (`ddl-auto=none`). Así las restricciones del backend son exactamente las del DDL que se exporta.
- **Identificadores**: van entre comillas en el SQL y en Hibernate (`globally_quoted_identifiers`), para que nombres como `Order` o `User` no choquen con palabras reservadas.
- **Bugs del primer parcial corregidos**:
  - Las relaciones bidireccionales entraban en recursión infinita al serializar a JSON. Ahora las colecciones llevan `@JsonIgnore` y la FK anidada usa `@JsonIgnoreProperties`.
  - `PUT` hacía `save(datos)` y borraba los vínculos N:M y las FKs no enviadas. Ahora copia campo a campo sobre la entidad existente.
  - Las referencias a ids inexistentes daban 500. Ahora dan 400.
- **Contrato JSON de una FK**: `{"persona": {"id": 3}}` (objeto anidado). Es el que ya consumía la app Flutter de CU15.
- **Rutas N:M**: `GET /api/{a}/{id}/{b}`, `POST /api/{a}/{id}/{b}/{bId}` (201, o 409 si ya existe) y `DELETE` (204, o 404). Están en ambos sentidos.
- **Base de datos del proyecto generado**:
  - `docker compose up --build` levanta `postgres:15`, la última versión certificada por Flyway 9, que es la que trae Spring Boot 3.2.
  - Sin Docker, `mvn spring-boot:run` usa H2 en modo PostgreSQL.
- **Verificación real**: se compiló con Maven y se corrió la colección Postman con newman sobre H2 y sobre PostgreSQL 17 (92/92 aserciones), con un diagrama que tiene todos los casos (`backend/tests/diagrama_completo.py`).
- **Flutter (CU15)**: usa las mismas FKs. La herencia ya no genera un dropdown `personaId` (no es una FK) y en su lugar la subclase incluye los atributos heredados. La clase de asociación recibe sus dos referencias.
- **Exportaciones (RF-BASE-07)**: además de PDF, PNG y XMI, ahora se exporta SVG (en el navegador), DDL (el mismo SQL de la migración) y JSON (el diagrama tal cual se guarda).

## 3. Colaboración en tiempo real (RF-RT)

- **Diagrama: se reutiliza Yjs (CRDT) del primer parcial, sin reconstruirlo con un protocolo propio de `version`.**
  - El servidor mantiene el documento de cada sala y lo persiste.
  - Cada cambio viaja como una operación atómica por campo, nunca el diagrama entero.
  - El CRDT garantiza que dos personas editando a la vez terminen con el mismo diagrama, que es lo que pide el criterio de aceptación, y además conserva los cursores y el Ctrl+Z por usuario.
  - Al entrar o reconectar, la sincronización de Yjs entrega el estado completo, y la sala manda además `DIAGRAM_SNAPSHOT` con un contador `version` informativo.
  - Reconstruirlo con un protocolo propio arriesgaba degradar funciones del primer parcial (la regla de oro).
- **Chat, presencia e IA**: van por un segundo WebSocket JSON (`/ws/proyectos/{id}/sala`) con los eventos `type` / `payload` de la tabla de `documentacion-tecnica.md`. Se agregaron `USER_LEFT`, `PRESENCE_LIST`, `DIAGRAM_SNAPSHOT`, `AI_TYPING` y `ERROR`, y también `WELCOME`, `CHAT_HISTORY`, `CHAT_MESSAGE_UPDATED` y `AI_MODE_CHANGED`.
- **Arrastre de nodos**: Yjs manda solo las posiciones que cambian, y el estado final es idéntico en todos los clientes.
- **Grupos**:
  - El registro pide nombre personal y nombre de grupo. Si el grupo ya existe (sin distinguir mayúsculas, tildes ni espacios extra) te unís a él; si no, se crea.
  - La "sala por grupo" significa que los integrantes del grupo del dueño de un proyecto entran a su tablero igual que un colaborador.
  - Solo el dueño administra el proyecto: editarlo, borrarlo y gestionar colaboradores.
  - Se mantienen los colaboradores explícitos del primer parcial (CU05) para no perder funcionalidad.
- **Login**: por defecto se entra con **nombre personal + nombre de grupo + contraseña** (`POST /auth/login-grupo`); el login con email sigue disponible en otra pestaña. Para que no sea ambiguo, el nombre personal es único dentro de cada grupo (sin distinguir mayúsculas, tildes ni espacios): registrarse o renombrarse con un nombre ya usado en el grupo da 409. El grupo se elige al registrarse y se puede cambiar desde el perfil.
- **Persistencia**:
  - El chat se guarda en `mensajes_chat` y el modo de la IA en `proyectos.modo_ia`.
  - Si todos se desconectan mientras el Senior está respondiendo, la sala sigue viva hasta que termina y la respuesta queda guardada.

## 4. Desarrollador Senior (RF-IA)

- **Chat público**: hay un único chat público por proyecto. El panel privado del asistente del primer parcial (CU13) **se reemplazó** en la interfaz por este chat grupal, porque la consigna dice que no hay canales privados con la IA. El endpoint HTTP `/proyectos/{id}/agente` y su código siguen en el backend, pero la interfaz ya no lo usa. Los comandos de voz (CU11) siguen siendo independientes.
- **Cuándo responde**: si la mencionan con `@senior`, si el mensaje empieza con "Senior, …" o un saludo seguido de "senior", o si se activa el toggle "Preguntar al Senior".
- **Modo por defecto: automático**. Con él, el escenario 7.2 actualiza el diagrama sin un paso extra. Cualquier integrante puede cambiar el modo y todos ven el cambio.
- **Propuestas** (modo con confirmación):
  - Cualquier integrante puede aplicarlas o rechazarlas, y la primera decisión gana.
  - Al aplicarla se re-valida contra el diagrama **actual**. Si dejó de ser válida, se marca "fallida" y se avisa.
- **Mejoras medidas con Gemini real**:
  - Se agregaron reglas explícitas al prompt: no modificar el diagrama ante preguntas teóricas; "la clase anterior" es la última mencionada en el chat; texto plano sin Markdown.
  - Hay una corrección determinística en código de la orientación todo/parte. En la primera medición, Gemini a veces dibujaba la composición al revés.
- **Clase de asociación**: el Senior la usa cuando un N:M tiene atributos propios. Se verificó con "Estudiante–Curso con nota y fecha", que produjo `Inscripcion` como clase de asociación.

## 5. Backend generado (RF-BASE-08/09)

- El botón ahora se llama "Generar Backend y APIs". El `.zip` trae:
  - `docker-compose.yml` (PostgreSQL + API);
  - `Dockerfile` multi-stage;
  - README de 5 líneas;
  - Swagger;
  - colección de Postman;
  - migración Flyway.
- La colección de Postman se puede correr completa: guarda los ids en variables y ordena las peticiones según las dependencias de FK.
- Se eligió PostgreSQL 15 en el compose generado porque es la última versión que certifica Flyway 9 (la de Spring Boot 3.2). Con 17 funciona igual, pero Flyway muestra un aviso.
