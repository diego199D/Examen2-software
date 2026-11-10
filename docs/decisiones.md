# Decisiones del segundo parcial

Cuando la consigna era ambigua (o la especificación del docente no estaba en el repo), se eligió la opción más razonable y se documenta acá.

## 0. Contexto

- La especificación del docente (`docs/especificacion-parcial2.md`) **no estaba en el repositorio** cuando se hizo este trabajo. Las referencias a §6.1–§6.4 y a los escenarios §7 se resolvieron con lo que dice el prompt de trabajo. El esquema de eventos y la herramienta `apply_diagram_mutations` están definidos acá (secciones 3 y 4) y en `docs/documentacion-tecnica.md`.
- El nombre del grupo **no es fijo en el código**. Cada usuario se registra con su nombre y el nombre de su grupo, y la interfaz muestra siempre el grupo de quien está logueado.

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
