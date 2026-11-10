"""
Generador de un proyecto Spring Boot completo (CU08, reconstruido en el
segundo parcial) a partir del diagrama de clases guardado.

El .zip levanta sin escribir una línea de código:
- `docker compose up --build` → PostgreSQL + la API (puerto 8080), o
- `mvn spring-boot:run` → la API con H2 en memoria (modo PostgreSQL).

Contenido:
- Entidades JPA (Lombok), repositorios, servicios y controladores REST con
  CRUD completo por clase en `/api/{plural}` (201/204/404/400/409 correctos).
- Rutas de relación para cada N:M (con o sin clase de asociación):
  `GET|POST|DELETE /api/{a}/{id}/{b}[/{bId}]`, en ambos sentidos.
- Migración Flyway `V1__esquema_inicial.sql` (ver `generador_ddl.py`) con PK,
  FK, índices, UNIQUE y ON DELETE: es la fuente de verdad del esquema
  (`ddl-auto=none`), así las restricciones son exactamente las exportadas.
- Swagger UI / OpenAPI (springdoc) en `/swagger-ui.html` y `/v3/api-docs`.
- Colección Postman (`postman_collection.json`, ver `generador_postman.py`)
  que recorre todo el CRUD, los vínculos N:M y la integridad referencial.
- README de 5 líneas, Dockerfile y docker-compose.yml.

Mapeo del diagrama al modelo relacional: `app/services/modelo_relacional.py`
(1:1, 1:N, N:M, clase de asociación, herencia JOINED, ON DELETE por tipo).

Decisiones de serialización (evitan los bugs del primer parcial):
- Las colecciones (`@OneToMany`, `@ManyToMany`) y el lado inverso de un
  `@OneToOne` llevan `@JsonIgnore`: antes la relación bidireccional entraba
  en recursión infinita al serializar apenas había datos vinculados. Los
  N:M se consultan por sus rutas de relación.
- Una FK se serializa como el objeto referido anidado sin sus propias
  relaciones (`@JsonIgnoreProperties`) — mismo contrato `{"persona": {"id":
  3}}` que ya consume la app Flutter (CU15).
- `actualizar` carga la entidad existente y copia solo atributos y FKs: un
  PUT ya no borra los vínculos N:M ni deja en null lo que no se mandó.
- Las referencias se resuelven contra la BD: un id inexistente da 400, una
  FK obligatoria vacía da 400, y una violación de integridad al borrar da
  409 (handler global).

Limitaciones conocidas:
- Sin autenticación/JWT; CORS abierto (`/api/**`): pensado para pruebas.
- Pluralización heurística (vocal → +s, consonante → +es).
- Los métodos UML no se generan (el CRUD cubre las operaciones básicas).
- Una clase abstracta no expone POST/PUT (no se puede instanciar).
"""

from __future__ import annotations

import io
import zipfile

from app.models.clase_uml import ClaseUml
from app.models.proyecto import Proyecto
from app.models.relacion import Relacion
from app.services.diagrama import MULTIPLICIDADES_PLURALES  # noqa: F401  (reexportado: CU15)
from app.services.generador_ddl import generar_ddl
from app.services.generador_postman import generar_coleccion_postman
from app.services.identificadores import (  # noqa: F401  (reexportados: CU15, reportes)
    a_snake_case,
    nombre_campo_java,
    nombre_clase_java,
    pluralizar,
    ruta_api_clase,
    slug_paquete,
)
from app.services.modelo_relacional import (  # noqa: F401  (reexportados: CU15)
    ClaveForanea,
    Entidad,
    ModeloRelacional,
    MuchosAMuchos,
    NombresRelacion,
    construir_modelo,
    resolver_nombres_relaciones,
)
from app.services.tipos import (  # noqa: F401  (reexportados)
    IMPORTS_POR_TIPO_JAVA,
    MAPEO_TIPOS_JAVA,
    mapear_tipo_java,
    tipo_no_reconocido,
)


def _cap(nombre: str) -> str:
    return nombre[:1].upper() + nombre[1:]


def _getter(campo: str) -> str:
    return f"get{_cap(campo)}"


def _setter(campo: str) -> str:
    return f"set{_cap(campo)}"


def _repo_var(nombre_java: str) -> str:
    return nombre_campo_java(nombre_java) + "Repository"


# ---------------------------------------------------------------------------
# Entidad
# ---------------------------------------------------------------------------


def _campos_relacion_de(modelo: ModeloRelacional, id_clase: str) -> list[str]:
    """Campos de relación (de cualquier tipo) que tiene una clase, incluidos
    los heredados — se ignoran al anidarla dentro de otra entidad en el JSON."""
    ids = {id_clase} | {a.clase.id for a in modelo.ancestros(id_clase)}
    campos: list[str] = []
    for k in modelo.claves:
        if k.id_entidad in ids:
            campos.append(k.campo)
        if k.id_referida in ids:
            campos.append(k.campo_inverso)
    for m in modelo.muchos_a_muchos:
        if m.id_asociacion is None:
            if m.id_dueño in ids:
                campos.append(m.campo_dueño)
            if m.id_inverso in ids:
                campos.append(m.campo_inverso)
    return sorted(set(campos))


def _renderizar_entidad(modelo: ModeloRelacional, e: Entidad, paquete: str) -> str:
    cid = e.clase.id
    imports = {
        "jakarta.persistence.*",
        "lombok.Getter",
        "lombok.NoArgsConstructor",
        "lombok.Setter",
    }
    cuerpo: list[str] = []
    anotaciones_clase = ["@Entity", f'@Table(name = "{e.tabla}"' + "{unique})"]
    unique = ""

    if e.ids_hijos:
        anotaciones_clase.append("@Inheritance(strategy = InheritanceType.JOINED)")
    if e.id_padre:
        anotaciones_clase.append('@PrimaryKeyJoinColumn(name = "id")')
    anotaciones_clase += ["@Getter", "@Setter", "@NoArgsConstructor"]

    for aviso in e.avisos:
        cuerpo.append(f"    // {aviso}")
    if not e.id_padre:
        cuerpo += [
            "    @Id",
            "    @GeneratedValue(strategy = GenerationType.IDENTITY)",
            '    @Column(name = "id")',
            "    private Long id;",
            "",
        ]
    for a in e.atributos:
        if a.tipo_java in IMPORTS_POR_TIPO_JAVA:
            imports.add(IMPORTS_POR_TIPO_JAVA[a.tipo_java])
        if a.aviso:
            cuerpo.append(f"    // {a.aviso}")
        cuerpo.append(f'    @Column(name = "{a.columna}")')
        cuerpo.append(f"    private {a.tipo_java} {a.nombre_campo};")
        cuerpo.append("")

    # FKs propias (lado dueño)
    columnas_asociacion: list[str] = []
    for k in modelo.claves_de(cid):
        ref = modelo.entidades[k.id_referida]
        imports.add("com.fasterxml.jackson.annotation.JsonIgnoreProperties")
        anot = "@OneToOne" if k.unica else "@ManyToOne"
        if k.obligatoria:
            anot += "(optional = false)"
        ignorar = ", ".join(f'"{c}"' for c in ["hibernateLazyInitializer", "handler", *_campos_relacion_de(modelo, ref.clase.id)])
        join = f'@JoinColumn(name = "{k.columna}"' + (", nullable = false" if k.obligatoria else "") + (", unique = true" if k.unica else "") + ")"
        cuerpo += [
            f"    // FK -> {ref.tabla}.id (ON DELETE {k.on_delete})",
            f"    {anot}",
            f"    {join}",
            f"    @JsonIgnoreProperties({{{ignorar}}})",
            f"    private {ref.nombre_java} {k.campo};",
            "",
        ]
        if k.de_asociacion:
            columnas_asociacion.append(k.columna)
    if len(columnas_asociacion) == 2:
        unique = (
            ", uniqueConstraints = @UniqueConstraint(columnNames = {"
            + ", ".join(f'"{c}"' for c in columnas_asociacion)
            + "})"
        )

    # Lados inversos (colecciones / OneToOne mappedBy)
    for k in modelo.claves_hacia(cid):
        hijo = modelo.entidades[k.id_entidad]
        imports.add("com.fasterxml.jackson.annotation.JsonIgnore")
        cascada = ", cascade = CascadeType.ALL, orphanRemoval = true" if k.composicion else ""
        if k.inverso_lista:
            imports.update({"java.util.List", "java.util.ArrayList"})
            cuerpo += [
                f'    @OneToMany(mappedBy = "{k.campo}"{cascada})',
                "    @JsonIgnore",
                f"    private List<{hijo.nombre_java}> {k.campo_inverso} = new ArrayList<>();",
                "",
            ]
        else:
            cuerpo += [
                f'    @OneToOne(mappedBy = "{k.campo}"{cascada})',
                "    @JsonIgnore",
                f"    private {hijo.nombre_java} {k.campo_inverso};",
                "",
            ]

    # N:M sin clase de asociación
    for m in modelo.mn_de(cid):
        if m.id_asociacion is not None:
            continue
        imports.update({"com.fasterxml.jackson.annotation.JsonIgnore", "java.util.Set", "java.util.HashSet"})
        if m.id_dueño == cid:
            otro = modelo.entidades[m.id_inverso]
            cuerpo += [
                f"    // N:M -> tabla intermedia {m.tabla} (PK compuesta, ON DELETE CASCADE)",
                "    @ManyToMany",
                "    @JoinTable(",
                f'        name = "{m.tabla}",',
                f'        joinColumns = @JoinColumn(name = "{m.columna_dueño}"),',
                f'        inverseJoinColumns = @JoinColumn(name = "{m.columna_inverso}")',
                "    )",
                "    @JsonIgnore",
                f"    private Set<{otro.nombre_java}> {m.campo_dueño} = new HashSet<>();",
                "",
            ]
        if m.id_inverso == cid:
            otro = modelo.entidades[m.id_dueño]
            cuerpo += [
                f'    @ManyToMany(mappedBy = "{m.campo_dueño}")',
                "    @JsonIgnore",
                f"    private Set<{otro.nombre_java}> {m.campo_inverso} = new HashSet<>();",
                "",
            ]

    extiende = ""
    if e.id_padre:
        padre = modelo.entidades[e.id_padre]
        extiende = f" extends {padre.nombre_java}"
    abstracta = "abstract " if e.abstracta else ""
    anotaciones_clase[1] = anotaciones_clase[1].replace("{unique}", unique)

    return (
        f"package {paquete}.model;\n\n"
        + "\n".join(f"import {i};" for i in sorted(imports))
        + "\n\n"
        + "\n".join(anotaciones_clase)
        + f"\npublic {abstracta}class {e.nombre_java}{extiende} {{\n\n"
        + "\n".join(cuerpo).rstrip()
        + "\n}\n"
    )


# ---------------------------------------------------------------------------
# Repositorio / servicio / controlador
# ---------------------------------------------------------------------------


def _renderizar_repository(modelo: ModeloRelacional, e: Entidad, paquete: str) -> str:
    extra: list[str] = []
    imports = {f"{paquete}.model.{e.nombre_java}", "org.springframework.data.jpa.repository.JpaRepository"}
    for m in modelo.muchos_a_muchos:
        if m.id_asociacion != e.clase.id:
            continue
        a, b = m.fk_asociacion_dueño, m.fk_asociacion_inverso
        imports.update({"java.util.List", "java.util.Optional"})
        extra += [
            f"    List<{e.nombre_java}> findBy{_cap(a.campo)}_Id(Long id);",
            f"    List<{e.nombre_java}> findBy{_cap(b.campo)}_Id(Long id);",
            f"    Optional<{e.nombre_java}> findBy{_cap(a.campo)}_IdAnd{_cap(b.campo)}_Id(Long a, Long b);",
        ]
    cuerpo = ("\n" + "\n".join(extra) + "\n") if extra else ""
    return (
        f"package {paquete}.repository;\n\n"
        + "\n".join(f"import {i};" for i in sorted(imports))
        + f"\n\npublic interface {e.nombre_java}Repository extends JpaRepository<{e.nombre_java}, Long> {{{cuerpo}}}\n"
    )


def _repos_necesarios(modelo: ModeloRelacional, e: Entidad) -> set[str]:
    """Nombres Java de las entidades cuyo repositorio usa el servicio de `e`."""
    res = {e.nombre_java}
    for k in modelo.claves_de(e.clase.id, heredadas=True):
        res.add(modelo.entidades[k.id_referida].nombre_java)
    for m in modelo.mn_de(e.clase.id):
        res.add(modelo.entidades[m.id_dueño].nombre_java)
        res.add(modelo.entidades[m.id_inverso].nombre_java)
        if m.id_asociacion:
            res.add(modelo.entidades[m.id_asociacion].nombre_java)
    return res


def _metodos_mn(modelo: ModeloRelacional, e: Entidad) -> tuple[list[str], list[str]]:
    """(métodos del servicio, métodos del controlador) de las rutas N:M de `e`."""
    serv: list[str] = []
    ctrl: list[str] = []
    var_repo = _repo_var(e.nombre_java)
    for m in modelo.mn_de(e.clase.id):
        for lado in ("dueño", "inverso"):
            if (m.id_dueño if lado == "dueño" else m.id_inverso) != e.clase.id:
                continue
            otro = modelo.entidades[m.id_inverso if lado == "dueño" else m.id_dueño]
            segmento = m.segmento_dueño if lado == "dueño" else m.segmento_inverso
            sufijo = _cap(nombre_campo_java(segmento.replace("-", " ")))
            repo_otro = _repo_var(otro.nombre_java)
            otro_id = nombre_campo_java(otro.nombre_java) + "Id"

            if m.id_asociacion:
                asoc = modelo.entidades[m.id_asociacion]
                repo_asoc = _repo_var(asoc.nombre_java)
                fk_yo = m.fk_asociacion_dueño if lado == "dueño" else m.fk_asociacion_inverso
                fk_otro = m.fk_asociacion_inverso if lado == "dueño" else m.fk_asociacion_dueño
                a_par = (
                    ("id", otro_id) if lado == "dueño" else (otro_id, "id")
                )
                serv += [
                    f"    public List<{otro.nombre_java}> listar{sufijo}(Long id) {{",
                    "        obtener(id);",
                    f"        return {repo_asoc}.findBy{_cap(fk_yo.campo)}_Id(id).stream().map({asoc.nombre_java}::{_getter(fk_otro.campo)}).toList();",
                    "    }",
                    "",
                    f"    public {asoc.nombre_java} vincular{sufijo}(Long id, Long {otro_id}) {{",
                    f"        {e.nombre_java} yo = obtener(id);",
                    f'        {otro.nombre_java} otro = {repo_otro}.findById({otro_id}).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "{otro.nombre_java} " + {otro_id} + " no existe"));',
                    f"        if ({repo_asoc}.findBy{_cap(m.fk_asociacion_dueño.campo)}_IdAnd{_cap(m.fk_asociacion_inverso.campo)}_Id({a_par[0]}, {a_par[1]}).isPresent()) {{",
                    '            throw new ResponseStatusException(HttpStatus.CONFLICT, "El vínculo ya existe");',
                    "        }",
                    f"        {asoc.nombre_java} vinculo = new {asoc.nombre_java}();",
                    f"        vinculo.{_setter(fk_yo.campo)}(yo);",
                    f"        vinculo.{_setter(fk_otro.campo)}(otro);",
                    f"        return {repo_asoc}.save(vinculo);",
                    "    }",
                    "",
                    f"    public void desvincular{sufijo}(Long id, Long {otro_id}) {{",
                    f"        {asoc.nombre_java} vinculo = {repo_asoc}.findBy{_cap(m.fk_asociacion_dueño.campo)}_IdAnd{_cap(m.fk_asociacion_inverso.campo)}_Id({a_par[0]}, {a_par[1]})",
                    '                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "El vínculo no existe"));',
                    f"        {repo_asoc}.delete(vinculo);",
                    "    }",
                    "",
                ]
                tipo_creado = asoc.nombre_java
            else:
                # El dueño JPA es quien escribe la tabla intermedia.
                if lado == "dueño":
                    cuerpo_v = [
                        f"        {e.nombre_java} yo = obtener(id);",
                        f'        {otro.nombre_java} otro = {repo_otro}.findById({otro_id}).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "{otro.nombre_java} " + {otro_id} + " no existe"));',
                        f"        if (!yo.{_getter(m.campo_dueño)}().add(otro)) {{",
                        '            throw new ResponseStatusException(HttpStatus.CONFLICT, "El vínculo ya existe");',
                        "        }",
                        f"        {var_repo}.save(yo);",
                        "        return otro;",
                    ]
                    cuerpo_d = [
                        f"        {e.nombre_java} yo = obtener(id);",
                        f"        if (!yo.{_getter(m.campo_dueño)}().removeIf(x -> x.getId().equals({otro_id}))) {{",
                        '            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "El vínculo no existe");',
                        "        }",
                        f"        {var_repo}.save(yo);",
                    ]
                    coleccion = m.campo_dueño
                else:
                    cuerpo_v = [
                        f"        {e.nombre_java} yo = obtener(id);",
                        f'        {otro.nombre_java} otro = {repo_otro}.findById({otro_id}).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "{otro.nombre_java} " + {otro_id} + " no existe"));',
                        f"        if (!otro.{_getter(m.campo_dueño)}().add(yo)) {{",
                        '            throw new ResponseStatusException(HttpStatus.CONFLICT, "El vínculo ya existe");',
                        "        }",
                        f"        {repo_otro}.save(otro);",
                        "        return otro;",
                    ]
                    cuerpo_d = [
                        "        obtener(id);",
                        f'        {otro.nombre_java} otro = {repo_otro}.findById({otro_id}).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "{otro.nombre_java} " + {otro_id} + " no existe"));',
                        f"        if (!otro.{_getter(m.campo_dueño)}().removeIf(x -> x.getId().equals(id))) {{",
                        '            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "El vínculo no existe");',
                        "        }",
                        f"        {repo_otro}.save(otro);",
                    ]
                    coleccion = m.campo_inverso
                serv += [
                    f"    public List<{otro.nombre_java}> listar{sufijo}(Long id) {{",
                    f"        return List.copyOf(obtener(id).{_getter(coleccion)}());",
                    "    }",
                    "",
                    f"    public {otro.nombre_java} vincular{sufijo}(Long id, Long {otro_id}) {{",
                    *cuerpo_v,
                    "    }",
                    "",
                    f"    public void desvincular{sufijo}(Long id, Long {otro_id}) {{",
                    *cuerpo_d,
                    "    }",
                    "",
                ]
                tipo_creado = otro.nombre_java

            ctrl += [
                f'    @Operation(summary = "Lista los {otro.nombre_java} vinculados (N:M)")',
                f'    @GetMapping("/{{id}}/{segmento}")',
                f"    public List<{otro.nombre_java}> listar{sufijo}(@PathVariable Long id) {{",
                f"        return service.listar{sufijo}(id);",
                "    }",
                "",
                f'    @Operation(summary = "Vincula un {otro.nombre_java} (N:M)")',
                f'    @PostMapping("/{{id}}/{segmento}/{{{otro_id}}}")',
                "    @ResponseStatus(HttpStatus.CREATED)",
                f"    public {tipo_creado} vincular{sufijo}(@PathVariable Long id, @PathVariable Long {otro_id}) {{",
                f"        return service.vincular{sufijo}(id, {otro_id});",
                "    }",
                "",
                f'    @Operation(summary = "Desvincula un {otro.nombre_java} (N:M)")',
                f'    @DeleteMapping("/{{id}}/{segmento}/{{{otro_id}}}")',
                "    @ResponseStatus(HttpStatus.NO_CONTENT)",
                f"    public void desvincular{sufijo}(@PathVariable Long id, @PathVariable Long {otro_id}) {{",
                f"        service.desvincular{sufijo}(id, {otro_id});",
                "    }",
                "",
            ]
    return serv, ctrl


def _renderizar_service(modelo: ModeloRelacional, e: Entidad, paquete: str) -> str:
    n = e.nombre_java
    var_repo = _repo_var(n)
    repos = sorted(_repos_necesarios(modelo, e))
    claves = modelo.claves_de(e.clase.id, heredadas=True)

    lineas_repos = []
    imports = {
        f"{paquete}.model.*",
        f"{paquete}.repository.*",
        "org.springframework.beans.factory.annotation.Autowired",
        "org.springframework.http.HttpStatus",
        "org.springframework.stereotype.Service",
        "org.springframework.transaction.annotation.Transactional",
        "org.springframework.web.server.ResponseStatusException",
        "java.util.List",
    }
    for r in repos:
        lineas_repos += ["    @Autowired", f"    private {r}Repository {_repo_var(r)};", ""]

    resolver: list[str] = []
    for k in claves:
        ref = modelo.entidades[k.id_referida]
        g, s_ = _getter(k.campo), _setter(k.campo)
        if k.obligatoria:
            resolver += [
                f"        if (origen.{g}() == null || origen.{g}().getId() == null) {{",
                f'            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "{k.campo} es obligatorio: enviar {{\\"{k.campo}\\": {{\\"id\\": ...}}}}");',
                "        }",
            ]
        resolver += [
            f"        destino.{s_}(origen.{g}() == null || origen.{g}().getId() == null ? null",
            f"                : {_repo_var(ref.nombre_java)}.findById(origen.{g}().getId())",
            f'                        .orElseThrow(() -> new ResponseStatusException(HttpStatus.BAD_REQUEST, "{ref.nombre_java} con id " + origen.{g}().getId() + " no existe")));',
        ]

    copiar = [
        f"        existente.{_setter(a.nombre_campo)}(datos.{_getter(a.nombre_campo)}());"
        for a in modelo.atributos_totales(e.clase.id)
    ]
    crud_escritura: list[str] = []
    if not e.abstracta:
        crud_escritura = [
            f"    public {n} crear({n} datos) {{",
            "        datos.setId(null);",
            "        resolverReferencias(datos, datos);",
            f"        return {var_repo}.save(datos);",
            "    }",
            "",
            f"    public {n} actualizar(Long id, {n} datos) {{",
            f"        {n} existente = obtener(id);",
            *copiar,
            "        resolverReferencias(datos, existente);",
            f"        return {var_repo}.save(existente);",
            "    }",
            "",
            f"    private void resolverReferencias({n} origen, {n} destino) {{",
            *resolver,
            "    }",
            "",
        ]
    serv_mn, _ = _metodos_mn(modelo, e)

    cuerpo = [
        *lineas_repos,
        f"    public List<{n}> listar() {{",
        f"        return {var_repo}.findAll();",
        "    }",
        "",
        f"    public {n} obtener(Long id) {{",
        f'        return {var_repo}.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "{n} " + id + " no existe"));',
        "    }",
        "",
        *crud_escritura,
        "    public void eliminar(Long id) {",
        f"        {var_repo}.delete(obtener(id));",
        f"        {var_repo}.flush();",
        "    }",
        "",
        *serv_mn,
    ]
    return (
        f"package {paquete}.service;\n\n"
        + "\n".join(f"import {i};" for i in sorted(imports))
        + f"\n\n@Service\n@Transactional\npublic class {n}Service {{\n\n"
        + "\n".join(cuerpo).rstrip()
        + "\n}\n"
    )


def _renderizar_controller(modelo: ModeloRelacional, e: Entidad, paquete: str) -> str:
    n = e.nombre_java
    _, ctrl_mn = _metodos_mn(modelo, e)
    escritura: list[str] = []
    if not e.abstracta:
        escritura = [
            f'    @Operation(summary = "Crea un {n}")',
            "    @PostMapping",
            "    @ResponseStatus(HttpStatus.CREATED)",
            f"    public {n} crear(@RequestBody {n} datos) {{",
            "        return service.crear(datos);",
            "    }",
            "",
            f'    @Operation(summary = "Actualiza un {n}")',
            '    @PutMapping("/{id}")',
            f"    public {n} actualizar(@PathVariable Long id, @RequestBody {n} datos) {{",
            "        return service.actualizar(id, datos);",
            "    }",
            "",
        ]
    cuerpo = [
        "    @Autowired",
        f"    private {n}Service service;",
        "",
        f'    @Operation(summary = "Lista todos los {n}")',
        "    @GetMapping",
        f"    public List<{n}> listar() {{",
        "        return service.listar();",
        "    }",
        "",
        f'    @Operation(summary = "Obtiene un {n} por id")',
        '    @GetMapping("/{id}")',
        f"    public {n} obtener(@PathVariable Long id) {{",
        "        return service.obtener(id);",
        "    }",
        "",
        *escritura,
        f'    @Operation(summary = "Elimina un {n}")',
        '    @DeleteMapping("/{id}")',
        "    @ResponseStatus(HttpStatus.NO_CONTENT)",
        "    public void eliminar(@PathVariable Long id) {",
        "        service.eliminar(id);",
        "    }",
        "",
        *ctrl_mn,
    ]
    return f"""package {paquete}.controller;

import {paquete}.model.*;
import {paquete}.service.{n}Service;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/{e.ruta}")
@Tag(name = "{n}")
public class {n}Controller {{

""" + "\n".join(cuerpo).rstrip() + "\n}\n"


# ---------------------------------------------------------------------------
# Archivos de proyecto
# ---------------------------------------------------------------------------


def _renderizar_pom(slug: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.5</version>
        <relativePath/>
    </parent>

    <groupId>com.generado</groupId>
    <artifactId>{slug}</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>{slug}</name>
    <description>Backend generado automáticamente a partir del diagrama de clases</description>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.flywaydb</groupId>
            <artifactId>flyway-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>2.5.0</version>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <excludes>
                        <exclude>
                            <groupId>org.projectlombok</groupId>
                            <artifactId>lombok</artifactId>
                        </exclude>
                    </excludes>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
"""


def _renderizar_application_properties(slug: str) -> str:
    return f"""# Generado automáticamente por Diagramador UML.
# Sin variables de entorno usa H2 en memoria (modo PostgreSQL): `mvn spring-boot:run`
# levanta sin instalar nada. docker-compose.yml define SPRING_DATASOURCE_* para
# usar PostgreSQL de verdad (persistente).
spring.datasource.url=${{SPRING_DATASOURCE_URL:jdbc:h2:mem:{slug};DB_CLOSE_DELAY=-1;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DEFAULT_NULL_ORDERING=HIGH}}
spring.datasource.username=${{SPRING_DATASOURCE_USERNAME:sa}}
spring.datasource.password=${{SPRING_DATASOURCE_PASSWORD:}}

# El esquema (PK, FK, índices, ON DELETE) lo crea la migración Flyway
# src/main/resources/db/migration/V1__esquema_inicial.sql -- Hibernate no lo toca.
spring.jpa.hibernate.ddl-auto=none
spring.flyway.enabled=true
spring.jpa.properties.hibernate.globally_quoted_identifiers=true
spring.jpa.open-in-view=true

# Mensajes de error legibles en las respuestas 4xx (útil desde Postman).
server.error.include-message=always

# Swagger UI: http://localhost:8080/swagger-ui.html  ·  OpenAPI: /v3/api-docs
springdoc.swagger-ui.path=/swagger-ui.html

# Consola H2 (solo con H2): http://localhost:8080/h2-console  (JDBC URL: jdbc:h2:mem:{slug}, usuario sa)
spring.h2.console.enabled=true
"""


def _renderizar_main(paquete: str) -> str:
    return f"""package {paquete};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackendApplication {{

    public static void main(String[] args) {{
        SpringApplication.run(BackendApplication.class, args);
    }}
}}
"""


def _renderizar_cors_config(paquete: str) -> str:
    return f"""package {paquete}.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** CORS abierto sobre /api/** para pruebas locales (no usar tal cual en producción). */
@Configuration
public class CorsConfig implements WebMvcConfigurer {{

    @Override
    public void addCorsMappings(CorsRegistry registry) {{
        registry.addMapping("/api/**")
                .allowedOriginPatterns("*")
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
                .allowedHeaders("*");
    }}
}}
"""


def _renderizar_manejador_errores(paquete: str) -> str:
    return f"""package {paquete}.config;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

/** Traduce errores de integridad referencial y de JSON a respuestas 409/400 claras. */
@RestControllerAdvice
public class ManejadorErrores {{

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<Map<String, Object>> integridad(DataIntegrityViolationException ex) {{
        return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of(
                "status", 409,
                "error", "Conflicto de integridad referencial",
                "message", "La operación viola una restricción (FK, UNIQUE o NOT NULL). "
                        + "Si intentás borrar un registro, puede que otros lo referencien."));
    }}

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, Object>> jsonInvalido(HttpMessageNotReadableException ex) {{
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of(
                "status", 400,
                "error", "JSON inválido",
                "message", "El cuerpo de la petición no es un JSON válido para esta entidad."));
    }}
}}
"""


def _renderizar_dockerfile() -> str:
    return """FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
"""


def _renderizar_docker_compose(slug: str) -> str:
    return f"""services:
  db:
    # 15: última versión de PostgreSQL certificada por Flyway 9 (Spring Boot 3.2).
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: {slug}
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
    volumes:
      - datos:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d {slug}"]
      interval: 3s
      retries: 20

  api:
    build: .
    depends_on:
      db:
        condition: service_healthy
    environment:
      SPRING_DATASOURCE_URL: jdbc:postgresql://db:5432/{slug}
      SPRING_DATASOURCE_USERNAME: app
      SPRING_DATASOURCE_PASSWORD: app
    ports:
      - "8080:8080"

volumes:
  datos:
"""


def _renderizar_readme(nombre_proyecto: str, slug: str) -> str:
    return f"""# {slug} — backend generado de "{nombre_proyecto}"
1. Levantar con BD incluida: `docker compose up --build` (o sin Docker: `mvn spring-boot:run`, usa H2 en memoria; requiere Java 17 + Maven).
2. API en http://localhost:8080/api — Swagger UI en http://localhost:8080/swagger-ui.html (OpenAPI en `/v3/api-docs`).
3. Postman: importar `postman_collection.json` y ejecutar la colección completa (Run): crea, vincula N:M, prueba la integridad y borra.
4. Esquema SQL (PK, FK, índices, tablas intermedias N:M): `src/main/resources/db/migration/V1__esquema_inicial.sql` (lo aplica Flyway al arrancar).
5. Sin autenticación y con CORS abierto: pensado para pruebas locales, no para producción.
"""


def generar_zip_backend(proyecto: Proyecto, clases: list[ClaseUml], relaciones: list[Relacion]) -> bytes:
    slug = slug_paquete(proyecto.nombre)
    paquete = f"com.generado.{slug}"
    dir_java = f"{slug}/src/main/java/{paquete.replace('.', '/')}"
    modelo = construir_modelo(clases, relaciones)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{slug}/pom.xml", _renderizar_pom(slug))
        zf.writestr(f"{slug}/README.md", _renderizar_readme(proyecto.nombre, slug))
        zf.writestr(f"{slug}/Dockerfile", _renderizar_dockerfile())
        zf.writestr(f"{slug}/docker-compose.yml", _renderizar_docker_compose(slug))
        zf.writestr(f"{slug}/.dockerignore", "target\n")
        zf.writestr(f"{slug}/postman_collection.json", generar_coleccion_postman(proyecto.nombre, modelo))
        zf.writestr(f"{slug}/src/main/resources/application.properties", _renderizar_application_properties(slug))
        zf.writestr(
            f"{slug}/src/main/resources/db/migration/V1__esquema_inicial.sql",
            generar_ddl(proyecto.nombre, modelo),
        )
        zf.writestr(f"{dir_java}/BackendApplication.java", _renderizar_main(paquete))
        zf.writestr(f"{dir_java}/config/CorsConfig.java", _renderizar_cors_config(paquete))
        zf.writestr(f"{dir_java}/config/ManejadorErrores.java", _renderizar_manejador_errores(paquete))

        for e in modelo.ordenadas():
            n = e.nombre_java
            zf.writestr(f"{dir_java}/model/{n}.java", _renderizar_entidad(modelo, e, paquete))
            zf.writestr(f"{dir_java}/repository/{n}Repository.java", _renderizar_repository(modelo, e, paquete))
            zf.writestr(f"{dir_java}/service/{n}Service.java", _renderizar_service(modelo, e, paquete))
            zf.writestr(f"{dir_java}/controller/{n}Controller.java", _renderizar_controller(modelo, e, paquete))

    return buffer.getvalue()
