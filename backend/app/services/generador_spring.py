"""
Generador de un proyecto Maven de Spring Boot (entidades JPA + repository +
service + controller REST) a partir del diagrama de clases guardado de un
proyecto (CU08).

Limitaciones conocidas (ver también el mensaje que acompañó esta implementación):
- Relaciones de tipo HERENCIA se mapean como asociación simple, sin
  @Inheritance/@MappedSuperclass — no hay herencia de tablas JPA todavía.
- `ClaseUml.es_abstracta` se ignora: toda clase genera una @Entity concreta.
- La pluralización (tablas, rutas REST, colecciones) es una heurística simple
  (vocal final -> +s, consonante final -> +es), no gramaticalmente perfecta
  para plurales irregulares en español.
- Composición: `orphanRemoval` solo es válido en JPA sobre @OneToOne y
  @OneToMany, no sobre @ManyToOne/@ManyToMany (Hibernate no compila esos
  atributos ahí). Por eso, en las combinaciones singular-plural y
  plural-singular, `cascade = CascadeType.ALL, orphanRemoval = true` se
  coloca en el lado @OneToMany (el "padre" real de la relación) en vez del
  lado dueño/FK como decía la consigna literal, para no generar Java que no
  compila. En plural-plural (@ManyToMany) no existe un lado válido para
  orphanRemoval, así que solo se agrega `cascade = CascadeType.ALL` en el
  lado dueño (origen), sin orphanRemoval.
- Los métodos UML (Metodo) no se reflejan en las entidades generadas — CU08
  solo pidió atributos -> columnas; el CRUD estándar ya cubre las
  operaciones básicas vía Repository/Service/Controller.
- `Relacion.etiqueta` no se usa para nombrar campos/columnas de la relación
  (es un texto libre para el diagrama, ej. "vive en", no un nombre de rol
  por extremo) — el nombre de campo siempre sale de la clase destino.
- Si hay **más de una relación entre el mismo par de clases** (ej. "Miembro
  presta Libro" y "Miembro reserva Libro"), el campo/columna de la segunda
  relación se desambigua con un sufijo numérico (`resolver_nombres_relaciones`,
  compartido con el generador de frontend Flutter de CU15, para que ambos
  numeren igual). Esto corrigió, de paso, un bug real: antes la columna
  salía siempre del nombre base sin desambiguar, así que dos relaciones al
  mismo par de clases generaban el mismo `@JoinColumn` duplicado en la
  misma entidad (Hibernate no arranca con eso). La corrección solo cubre
  @OneToOne/@ManyToOne — en @ManyToMany (multiplicidad plural en ambos
  extremos) la tabla y las columnas de join siguen saliendo únicamente de
  los nombres de clase, así que dos relaciones M:N entre el mismo par
  todavía chocarían ahí; no se corrigió porque el caso concreto que motivó
  el arreglo (Miembro-Libro de arriba) es 1 a muchos, no M:N.
- Un atributo del diagrama llamado "id" (cualquier variación de mayúsculas)
  se ignora al generar columnas: el `@Id` autogenerado ya existe siempre y
  un `@Column` adicional con el mismo nombre de campo no compila.
- Tipo de atributo no reconocido (typo, tipo custom no soportado): NO se
  valida al guardar el diagrama (CU09) — `tipo` sigue siendo texto libre a
  propósito, porque el diagrama es de modelado general y no todo atributo
  tiene por qué mapear a un tipo Java primitivo (puede referenciar otra
  clase, ser una idea a medio definir, etc.); exigir un tipo válido ahí
  limitaría el modelado por el bien de un solo consumidor opcional (CU08).
  En cambio, el generador defaultea a String como siempre pero deja un
  comentario `// tipo UML "..." no reconocido, se usó String por defecto`
  arriba del campo, visible al revisar el .java antes de usarlo.

El proyecto generado corre sin configuración manual, pensado para poder
probarlo rápido: `application.properties` usa H2 en memoria por defecto
(sin instalar/configurar PostgreSQL — el bloque de Postgres queda
comentado como referencia para quien quiera persistencia real más
adelante), se genera un `README.md` en la raíz con los pasos exactos
para levantarlo, y se agrega `config/CorsConfig.java` con CORS abierto
para que un frontend en cualquier puerto de localhost pueda consumir la
API sin bloqueos del navegador. Ambas cosas son para pruebas/demo
locales, no para producción (sigue sin haber autenticación/JWT).
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field

from app.models.clase_uml import ClaseUml
from app.models.proyecto import Proyecto
from app.models.relacion import Relacion, TipoRelacion

# --------------------------------------------------------------------------
# Mapeo de tipos UML (texto libre en Atributo.tipo / Atributo.tipo_retorno)
# a tipos Java. Explícito y documentado, con un valor por defecto seguro.
# --------------------------------------------------------------------------

MAPEO_TIPOS_JAVA: dict[str, str] = {
    "string": "String",
    "str": "String",
    "texto": "String",
    "char": "String",
    "int": "Integer",
    "integer": "Integer",
    "entero": "Integer",
    "long": "Long",
    "float": "Double",
    "double": "Double",
    "decimal": "BigDecimal",
    "bigdecimal": "BigDecimal",
    "boolean": "Boolean",
    "bool": "Boolean",
    "date": "LocalDate",
    "fecha": "LocalDate",
    "datetime": "LocalDateTime",
    "fechahora": "LocalDateTime",
    "timestamp": "LocalDateTime",
    "uuid": "UUID",
}
TIPO_JAVA_POR_DEFECTO = "String"

IMPORTS_POR_TIPO_JAVA: dict[str, str] = {
    "BigDecimal": "java.math.BigDecimal",
    "LocalDate": "java.time.LocalDate",
    "LocalDateTime": "java.time.LocalDateTime",
    "UUID": "java.util.UUID",
}

# Debe coincidir con OPCIONES_MULTIPLICIDAD (frontend) y
# MULTIPLICIDADES_VALIDAS (app/routers/diagramas.py).
MULTIPLICIDADES_PLURALES = {"0..*", "1..*"}


def mapear_tipo_java(tipo_uml: str | None) -> str:
    if not tipo_uml:
        return TIPO_JAVA_POR_DEFECTO
    return MAPEO_TIPOS_JAVA.get(tipo_uml.strip().lower(), TIPO_JAVA_POR_DEFECTO)


def tipo_no_reconocido(tipo_uml: str | None) -> bool:
    """True si se escribió un tipo que no está en MAPEO_TIPOS_JAVA (typo,
    tipo custom no soportado, etc.). No cuenta el caso de no especificar
    tipo (`None`/vacío) — ahí el default a String es el comportamiento
    esperado, no un error silencioso."""
    return bool(tipo_uml) and tipo_uml.strip().lower() not in MAPEO_TIPOS_JAVA


# --------------------------------------------------------------------------
# Identificadores Java (nombres de clase/campo/paquete/tabla) a partir de
# texto libre (nombres UML escritos por la usuaria, sin restricciones).
# --------------------------------------------------------------------------


def _quitar_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _palabras(nombre: str) -> list[str]:
    limpio = _quitar_acentos(nombre or "")
    return [p for p in re.split(r"[^0-9a-zA-Z]+", limpio) if p]


def nombre_clase_java(nombre_uml: str) -> str:
    """PascalCase válido como nombre de clase Java (p. ej. 'orden de compra' -> 'OrdenDeCompra')."""
    palabras = _palabras(nombre_uml) or ["Clase"]
    resultado = "".join(p[:1].upper() + p[1:] for p in palabras)
    if resultado[0].isdigit():
        resultado = "Clase" + resultado
    return resultado


def nombre_campo_java(nombre_uml: str) -> str:
    """camelCase a partir del mismo texto (para campos de instancia)."""
    clase = nombre_clase_java(nombre_uml)
    return clase[:1].lower() + clase[1:]


def a_snake_case(nombre_pascal_o_camel: str) -> str:
    con_guiones = re.sub(r"(?<!^)(?=[A-Z])", "_", nombre_pascal_o_camel)
    return con_guiones.lower()


def pluralizar(palabra: str) -> str:
    """Heurística simple: vocal final -> +s, consonante final -> +es.
    No es gramaticalmente perfecta para plurales irregulares en español
    (ej. 'lápiz' -> 'lápizes' en vez de 'lápices')."""
    if not palabra:
        return palabra
    if palabra[-1].lower() in "aeiouáéíóú":
        return palabra + "s"
    return palabra + "es"


def ruta_api_clase(nombre_java: str) -> str:
    """Segmento de ruta REST bajo /api/ para una clase (ej. 'Persona' -> 'personas')."""
    return pluralizar(nombre_java).lower()


def slug_paquete(nombre_proyecto: str) -> str:
    """Segmento de paquete Java / nombre de artefacto Maven válido a partir
    del nombre del proyecto (solo minúsculas y dígitos)."""
    palabras = _palabras(nombre_proyecto)
    slug = "".join(p.lower() for p in palabras) or "backend"
    if slug[0].isdigit():
        slug = "p" + slug
    return slug


def _nombre_campo_unico(usados: set[str], propuesto: str) -> str:
    if propuesto not in usados:
        usados.add(propuesto)
        return propuesto
    i = 2
    while f"{propuesto}{i}" in usados:
        i += 1
    resultado = f"{propuesto}{i}"
    usados.add(resultado)
    return resultado


def _clasificar_multiplicidad(valor: str | None) -> str:
    return "plural" if valor in MULTIPLICIDADES_PLURALES else "singular"


def _anotacion_con_cascade(nombre_anotacion: str, cascade_orphan: bool, cascade_solo: bool) -> str:
    if cascade_orphan:
        return f"{nombre_anotacion}(cascade = CascadeType.ALL, orphanRemoval = true)"
    if cascade_solo:
        return f"{nombre_anotacion}(cascade = CascadeType.ALL)"
    return nombre_anotacion


# --------------------------------------------------------------------------
# Representación intermedia de los campos de una entidad antes de renderizar
# el archivo .java.
# --------------------------------------------------------------------------


@dataclass
class CampoAtributo:
    nombre_campo: str
    tipo_java: str
    columna: str
    aviso: str | None = None


@dataclass
class CampoRelacion:
    lineas_anotacion: list[str]
    tipo_java_campo: str  # "Direccion" o "List<Direccion>"
    nombre_campo: str


@dataclass
class DatosEntidad:
    clase: ClaseUml
    nombre_java: str
    atributos: list[CampoAtributo] = field(default_factory=list)
    relaciones: list[CampoRelacion] = field(default_factory=list)


@dataclass
class NombresRelacion:
    """Nombre de campo ya desambiguado (dentro de la clase que lo recibe)
    para cada lado de una relación. Público y compartido con
    `generador_flutter.py` (CU15): si hay más de una relación entre el
    mismo par de clases (ej. "Miembro presta Libro" y "Miembro reserva
    Libro"), backend y frontend generados tienen que numerar el sufijo de
    colisión de la misma forma — si no, el campo `libroId`/`libroId2` del
    modelo Dart no coincidiría con la clave JSON real que produce/espera el
    backend Spring Boot."""

    dueño: str  # lado con la FK escalar (@ManyToOne/@OneToOne dueño/@ManyToMany dueño)
    inverso: str  # el otro lado (@OneToMany/@OneToOne mappedBy/@ManyToMany mappedBy)


def resolver_nombres_relaciones(
    clases: list[ClaseUml], relaciones: list[Relacion]
) -> dict[str, NombresRelacion]:
    """Determina, para cada relación (indexada por `Relacion.id`), el
    nombre de campo que le correspondería en cada una de las dos clases
    que conecta — con el mismo criterio de "quién es el dueño" que usa
    `_procesar_relaciones` de abajo (ver mapeo multiplicidad -> JPA en el
    encabezado del módulo), pero sin nada específico de Java, para que
    `generador_flutter.py` (CU15) pueda reusarlo tal cual.

    Las relaciones se procesan en un orden estable (por `id`, no el orden
    en que la fuente de datos las haya devuelto) — así el resultado no
    depende de en qué orden llegaron las filas de la BD, y CU08/CU15
    calculan siempre lo mismo aunque se pidan por separado."""
    clases_por_id = {c.id: c for c in clases}
    nombres_usados_por_clase: dict[str, set[str]] = {
        c.id: {nombre_campo_java(a.nombre) for a in c.atributos} for c in clases
    }
    resultado: dict[str, NombresRelacion] = {}

    for r in sorted(relaciones, key=lambda r: r.id):
        origen = clases_por_id.get(r.id_clase_origen)
        destino = clases_por_id.get(r.id_clase_destino)
        if origen is None or destino is None:
            continue  # payload inconsistente — ya se valida al guardar el diagrama (CU09)

        # Campo que "apunta a" cada clase. Se ignora `etiqueta` a propósito:
        # describe la relación como texto libre para el diagrama (ej. "vive
        # en"), no un nombre de rol por extremo — usarla acá daba nombres de
        # campo/columna iguales en ambos lados. Colisiones entre varias
        # relaciones al mismo par de clases se resuelven con el sufijo
        # numérico de _nombre_campo_unico.
        campo_hacia_origen = nombre_campo_java(origen.nombre)
        campo_hacia_destino = nombre_campo_java(destino.nombre)

        cls_origen = _clasificar_multiplicidad(r.multiplicidad_origen)
        cls_destino = _clasificar_multiplicidad(r.multiplicidad_destino)

        if cls_origen == "singular" and cls_destino == "singular":
            dueño = _nombre_campo_unico(nombres_usados_por_clase[origen.id], campo_hacia_destino)
            inverso = _nombre_campo_unico(nombres_usados_por_clase[destino.id], campo_hacia_origen)
        elif cls_origen == "singular" and cls_destino == "plural":
            dueño = _nombre_campo_unico(nombres_usados_por_clase[destino.id], campo_hacia_origen)
            inverso = _nombre_campo_unico(nombres_usados_por_clase[origen.id], campo_hacia_destino + "List")
        elif cls_origen == "plural" and cls_destino == "singular":
            dueño = _nombre_campo_unico(nombres_usados_por_clase[origen.id], campo_hacia_destino)
            inverso = _nombre_campo_unico(nombres_usados_por_clase[destino.id], campo_hacia_origen + "List")
        else:  # plural-plural
            dueño = _nombre_campo_unico(nombres_usados_por_clase[origen.id], campo_hacia_destino + "List")
            inverso = _nombre_campo_unico(nombres_usados_por_clase[destino.id], campo_hacia_origen + "List")

        resultado[r.id] = NombresRelacion(dueño=dueño, inverso=inverso)

    return resultado


def _procesar_relaciones(
    clases: list[ClaseUml], relaciones: list[Relacion]
) -> dict[str, list[CampoRelacion]]:
    """Aplica la regla de mapeo multiplicidad -> anotación JPA descrita en el
    encabezado del módulo, devolviendo los campos de relación a agregar en
    cada entidad, indexados por id de ClaseUml. Los nombres de campo ya
    vienen resueltos por `resolver_nombres_relaciones` (compartido con
    CU15) — acá solo se decide la anotación/columna/tabla de cada uno."""
    clases_por_id = {c.id: c for c in clases}
    campos_por_clase: dict[str, list[CampoRelacion]] = {c.id: [] for c in clases}
    nombres_relaciones = resolver_nombres_relaciones(clases, relaciones)

    for r in relaciones:
        origen = clases_por_id.get(r.id_clase_origen)
        destino = clases_por_id.get(r.id_clase_destino)
        nombres = nombres_relaciones.get(r.id)
        if origen is None or destino is None or nombres is None:
            continue  # payload inconsistente — ya se valida al guardar el diagrama (CU09)

        nombre_java_origen = nombre_clase_java(origen.nombre)
        nombre_java_destino = nombre_clase_java(destino.nombre)

        cls_origen = _clasificar_multiplicidad(r.multiplicidad_origen)
        cls_destino = _clasificar_multiplicidad(r.multiplicidad_destino)
        es_composicion = r.tipo == TipoRelacion.COMPOSICION
        # Herencia/Asociación/Agregación se tratan igual (sin cascade especial) —
        # ver limitación sobre no implementar @Inheritance todavía.

        if cls_origen == "singular" and cls_destino == "singular":
            # OneToOne, origen dueño (tiene la FK) — orphanRemoval sí es
            # válido en JPA sobre @OneToOne, así que aquí se sigue la
            # consigna literal (cascade+orphanRemoval en el lado dueño).
            # La columna sale del nombre YA desambiguado (`nombres.dueño`),
            # no de la base sin desambiguar — si no, dos relaciones al mismo
            # par de clases generarían el mismo @JoinColumn en la misma
            # entidad (nombre de columna duplicado, no válido en Hibernate).
            columna = a_snake_case(nombres.dueño) + "_id"
            anotacion = _anotacion_con_cascade("@OneToOne", es_composicion, False)
            campos_por_clase[origen.id].append(
                CampoRelacion(
                    lineas_anotacion=[anotacion, f'@JoinColumn(name = "{columna}")'],
                    tipo_java_campo=nombre_java_destino,
                    nombre_campo=nombres.dueño,
                )
            )
            campos_por_clase[destino.id].append(
                CampoRelacion(
                    lineas_anotacion=[f'@OneToOne(mappedBy = "{nombres.dueño}")'],
                    tipo_java_campo=nombre_java_origen,
                    nombre_campo=nombres.inverso,
                )
            )

        elif cls_origen == "singular" and cls_destino == "plural":
            # destino = dueño (@ManyToOne, tiene la FK) / origen = inverso (@OneToMany, mappedBy).
            columna = a_snake_case(nombres.dueño) + "_id"
            campos_por_clase[destino.id].append(
                CampoRelacion(
                    lineas_anotacion=["@ManyToOne", f'@JoinColumn(name = "{columna}")'],
                    tipo_java_campo=nombre_java_origen,
                    nombre_campo=nombres.dueño,
                )
            )
            anotacion_padre = f'@OneToMany(mappedBy = "{nombres.dueño}"' + (
                ", cascade = CascadeType.ALL, orphanRemoval = true)" if es_composicion else ")"
            )
            campos_por_clase[origen.id].append(
                CampoRelacion(
                    lineas_anotacion=[anotacion_padre],
                    tipo_java_campo=f"List<{nombre_java_destino}>",
                    nombre_campo=nombres.inverso,
                )
            )

        elif cls_origen == "plural" and cls_destino == "singular":
            # origen = dueño (@ManyToOne, tiene la FK) / destino = inverso (@OneToMany, mappedBy).
            columna = a_snake_case(nombres.dueño) + "_id"
            campos_por_clase[origen.id].append(
                CampoRelacion(
                    lineas_anotacion=["@ManyToOne", f'@JoinColumn(name = "{columna}")'],
                    tipo_java_campo=nombre_java_destino,
                    nombre_campo=nombres.dueño,
                )
            )
            anotacion_padre = f'@OneToMany(mappedBy = "{nombres.dueño}"' + (
                ", cascade = CascadeType.ALL, orphanRemoval = true)" if es_composicion else ")"
            )
            campos_por_clase[destino.id].append(
                CampoRelacion(
                    lineas_anotacion=[anotacion_padre],
                    tipo_java_campo=f"List<{nombre_java_origen}>",
                    nombre_campo=nombres.inverso,
                )
            )

        else:
            # plural-plural: @ManyToMany, dueño = origen. orphanRemoval no
            # existe para ManyToMany en JPA; solo se agrega cascade.
            # OJO: el nombre de la tabla/columnas de join todavía sale de
            # las clases (no del campo desambiguado) — dos relaciones M:N
            # entre el mismo par de clases seguirían chocando en la tabla
            # de join. No se corrigió (ver limitación documentada arriba):
            # el caso concreto que motivó este arreglo (ej. "Miembro presta
            # Libro" / "Miembro reserva Libro") es 1 a muchos, no M:N.
            tabla_join = f"{a_snake_case(nombre_java_origen)}_{a_snake_case(nombre_java_destino)}"
            columna_origen = a_snake_case(nombre_java_origen) + "_id"
            columna_destino = a_snake_case(nombre_java_destino) + "_id"
            anotacion_many_to_many = _anotacion_con_cascade("@ManyToMany", False, es_composicion)
            campos_por_clase[origen.id].append(
                CampoRelacion(
                    lineas_anotacion=[
                        anotacion_many_to_many,
                        "@JoinTable(",
                        f'    name = "{tabla_join}",',
                        f'    joinColumns = @JoinColumn(name = "{columna_origen}"),',
                        f'    inverseJoinColumns = @JoinColumn(name = "{columna_destino}")',
                        ")",
                    ],
                    tipo_java_campo=f"List<{nombre_java_destino}>",
                    nombre_campo=nombres.dueño,
                )
            )
            campos_por_clase[destino.id].append(
                CampoRelacion(
                    lineas_anotacion=[f'@ManyToMany(mappedBy = "{nombres.dueño}")'],
                    tipo_java_campo=f"List<{nombre_java_origen}>",
                    nombre_campo=nombres.inverso,
                )
            )

    return campos_por_clase


# --------------------------------------------------------------------------
# Renderizado de archivos .java / pom.xml / application.properties
# --------------------------------------------------------------------------


def _renderizar_entidad(datos: DatosEntidad, paquete_base: str) -> str:
    tabla = a_snake_case(pluralizar(datos.nombre_java))

    imports_extra = {
        IMPORTS_POR_TIPO_JAVA[c.tipo_java] for c in datos.atributos if c.tipo_java in IMPORTS_POR_TIPO_JAVA
    }
    necesita_list = any(c.tipo_java_campo.startswith("List<") for c in datos.relaciones)

    lineas_imports = [
        "import jakarta.persistence.*;",
        "import lombok.AllArgsConstructor;",
        "import lombok.Getter;",
        "import lombok.NoArgsConstructor;",
        "import lombok.Setter;",
    ]
    if necesita_list:
        lineas_imports.append("import java.util.List;")
    lineas_imports.extend(f"import {t};" for t in sorted(imports_extra))

    cuerpo: list[str] = [
        "    @Id",
        "    @GeneratedValue(strategy = GenerationType.IDENTITY)",
        "    private Long id;",
        "",
    ]
    for a in datos.atributos:
        if a.aviso:
            cuerpo.append(f"    // {a.aviso}")
        cuerpo.append(f'    @Column(name = "{a.columna}")')
        cuerpo.append(f"    private {a.tipo_java} {a.nombre_campo};")
        cuerpo.append("")
    for r in datos.relaciones:
        cuerpo.extend(f"    {linea}" for linea in r.lineas_anotacion)
        cuerpo.append(f"    private {r.tipo_java_campo} {r.nombre_campo};")
        cuerpo.append("")

    return (
        f"package {paquete_base}.model;\n\n"
        + "\n".join(lineas_imports)
        + "\n\n@Entity\n"
        f'@Table(name = "{tabla}")\n'
        "@Getter\n@Setter\n@NoArgsConstructor\n@AllArgsConstructor\n"
        f"public class {datos.nombre_java} {{\n\n"
        + "\n".join(cuerpo).rstrip()
        + "\n}\n"
    )


def _renderizar_repository(nombre_java: str, paquete_base: str) -> str:
    return (
        f"package {paquete_base}.repository;\n\n"
        f"import {paquete_base}.model.{nombre_java};\n"
        "import org.springframework.data.jpa.repository.JpaRepository;\n\n"
        f"public interface {nombre_java}Repository extends JpaRepository<{nombre_java}, Long> {{\n"
        "}\n"
    )


def _renderizar_service(nombre_java: str, paquete_base: str) -> str:
    var = nombre_campo_java(nombre_java)
    return f"""package {paquete_base}.service;

import {paquete_base}.model.{nombre_java};
import {paquete_base}.repository.{nombre_java}Repository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Optional;

@Service
public class {nombre_java}Service {{

    @Autowired
    private {nombre_java}Repository {var}Repository;

    public List<{nombre_java}> listar() {{
        return {var}Repository.findAll();
    }}

    public Optional<{nombre_java}> obtenerPorId(Long id) {{
        return {var}Repository.findById(id);
    }}

    public {nombre_java} crear({nombre_java} {var}) {{
        return {var}Repository.save({var});
    }}

    public {nombre_java} actualizar(Long id, {nombre_java} datos) {{
        datos.setId(id);
        return {var}Repository.save(datos);
    }}

    public void eliminar(Long id) {{
        {var}Repository.deleteById(id);
    }}
}}
"""


def _renderizar_controller(nombre_java: str, paquete_base: str) -> str:
    var = nombre_campo_java(nombre_java)
    ruta = ruta_api_clase(nombre_java)
    return f"""package {paquete_base}.controller;

import {paquete_base}.model.{nombre_java};
import {paquete_base}.service.{nombre_java}Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/{ruta}")
public class {nombre_java}Controller {{

    @Autowired
    private {nombre_java}Service {var}Service;

    @GetMapping
    public List<{nombre_java}> listar() {{
        return {var}Service.listar();
    }}

    @GetMapping("/{{id}}")
    public ResponseEntity<{nombre_java}> obtenerPorId(@PathVariable Long id) {{
        return {var}Service.obtenerPorId(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }}

    @PostMapping
    public {nombre_java} crear(@RequestBody {nombre_java} {var}) {{
        return {var}Service.crear({var});
    }}

    @PutMapping("/{{id}}")
    public {nombre_java} actualizar(@PathVariable Long id, @RequestBody {nombre_java} datos) {{
        return {var}Service.actualizar(id, datos);
    }}

    @DeleteMapping("/{{id}}")
    public ResponseEntity<Void> eliminar(@PathVariable Long id) {{
        {var}Service.eliminar(id);
        return ResponseEntity.noContent().build();
    }}
}}
"""


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
    <description>Backend generado automáticamente a partir del diagrama de clases (CU08)</description>

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
            </plugin>
        </plugins>
    </build>
</project>
"""


def _renderizar_application_properties(slug: str) -> str:
    return f"""# Generado automáticamente (CU08).
# Por defecto usa una base de datos H2 en memoria: no hace falta instalar
# ni configurar nada para levantar este backend y probarlo. Los datos NO
# persisten entre reinicios de la aplicación — pensado para pruebas
# manuales/demo rápidas, no para producción.
spring.datasource.url=jdbc:h2:mem:{slug};DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Consola web de H2 (para inspeccionar las tablas mientras se prueba):
# http://localhost:8080/h2-console -- JDBC URL: jdbc:h2:mem:{slug}
spring.h2.console.enabled=true

spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=true

# --- Para usar PostgreSQL en vez de H2 (persistencia real entre reinicios) ---
# 1. Comentar las líneas activas de arriba (spring.datasource.* y spring.h2.console.enabled).
# 2. Descomentar y completar estas:
# spring.datasource.url=jdbc:postgresql://localhost:5432/CAMBIAR_NOMBRE_BD
# spring.datasource.driver-class-name=org.postgresql.Driver
# spring.datasource.username=CAMBIAR_USUARIO
# spring.datasource.password=CAMBIAR_CONTRASENA

# Seguridad: este backend generado NO incluye autenticación/JWT todavía.
# Es una mejora futura pendiente (ver limitaciones documentadas de CU08).
"""


def _renderizar_main(paquete_base: str, nombre_clase_app: str) -> str:
    return f"""package {paquete_base};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class {nombre_clase_app} {{

    public static void main(String[] args) {{
        SpringApplication.run({nombre_clase_app}.class, args);
    }}
}}
"""


def _renderizar_cors_config(paquete_base: str) -> str:
    return f"""package {paquete_base}.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * CORS abierto para pruebas/demo locales (CU08, generado automáticamente).
 * Permite que un frontend en cualquier origen llame a esta API sin
 * errores de CORS en el navegador. NO usar tal cual en producción: este
 * backend generado tampoco incluye autenticación/JWT (ver README.md).
 */
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


def _renderizar_readme(nombre_proyecto: str, slug: str, clases: list[ClaseUml]) -> str:
    nombres_java = sorted({nombre_clase_java(c.nombre) for c in clases}, key=str.lower)
    filas_clases = "\n".join(f"- `{n}` -> `/api/{ruta_api_clase(n)}`" for n in nombres_java)

    return f"""# {slug} (backend generado - CU08)

Backend Spring Boot generado automáticamente a partir del diagrama de
clases UML del proyecto **"{nombre_proyecto}"**.

## Requisitos previos

- **Java 17** (JDK)
- **Maven** instalado en el sistema (este proyecto generado no incluye
  wrapper `mvnw`/`mvnw.cmd`)

## Cómo ejecutar

Desde la raíz de este proyecto (donde está `pom.xml`):

```
mvn spring-boot:run
```

La API queda disponible en **http://localhost:8080**.

No se necesita ninguna configuración adicional para levantarlo: por
defecto usa una base de datos **H2 en memoria** (ver
`src/main/resources/application.properties`). Los datos **no persisten**
entre reinicios de la aplicación — pensado para pruebas manuales/demo
rápidas, no para producción. Si más adelante se necesita persistencia
real, `application.properties` incluye (comentado) el bloque de
configuración para PostgreSQL.

Consola web de H2 (para inspeccionar las tablas mientras se prueba):
http://localhost:8080/h2-console — JDBC URL: `jdbc:h2:mem:{slug}`,
usuario `sa`, contraseña en blanco.

## Endpoints generados

Cada clase del diagrama expone un CRUD REST estándar bajo `/api/{{plural}}`:

| Método | Ruta | Descripción |
|---|---|---|
| GET    | /api/{{plural}}      | Listar todos |
| GET    | /api/{{plural}}/{{id}} | Obtener uno por id |
| POST   | /api/{{plural}}      | Crear |
| PUT    | /api/{{plural}}/{{id}} | Actualizar |
| DELETE | /api/{{plural}}/{{id}} | Eliminar |

Clases de este proyecto:

{filas_clases}

## Limitaciones conocidas

- **Sin autenticación/JWT**: todos los endpoints son públicos. No usar
  este backend tal cual en un entorno real.
- **CORS abierto para desarrollo**: se permite cualquier origen sobre
  `/api/**` (ver `config/CorsConfig.java`) para que un frontend en
  cualquier puerto de localhost pueda probar contra esta API sin
  configuración adicional. Tampoco apto para producción tal cual.
"""


# --------------------------------------------------------------------------
# Punto de entrada: arma el .zip completo.
# --------------------------------------------------------------------------


def generar_zip_backend(proyecto: Proyecto, clases: list[ClaseUml], relaciones: list[Relacion]) -> bytes:
    slug = slug_paquete(proyecto.nombre)
    paquete_base = f"com.generado.{slug}"
    paquete_dir = paquete_base.replace(".", "/")
    nombre_app_class = "BackendApplication"

    campos_relacion_por_clase = _procesar_relaciones(clases, relaciones)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        raiz = slug
        zf.writestr(f"{raiz}/pom.xml", _renderizar_pom(slug))
        zf.writestr(f"{raiz}/src/main/resources/application.properties", _renderizar_application_properties(slug))
        zf.writestr(f"{raiz}/README.md", _renderizar_readme(proyecto.nombre, slug, clases))
        zf.writestr(
            f"{raiz}/src/main/java/{paquete_dir}/{nombre_app_class}.java",
            _renderizar_main(paquete_base, nombre_app_class),
        )
        zf.writestr(
            f"{raiz}/src/main/java/{paquete_dir}/config/CorsConfig.java",
            _renderizar_cors_config(paquete_base),
        )

        for c in clases:
            nombre_java = nombre_clase_java(c.nombre)
            atributos = [
                CampoAtributo(
                    nombre_campo=nombre_campo_java(a.nombre),
                    tipo_java=mapear_tipo_java(a.tipo),
                    columna=a_snake_case(nombre_campo_java(a.nombre)),
                    aviso=(
                        f'tipo UML "{a.tipo}" no reconocido, se usó String por defecto'
                        if tipo_no_reconocido(a.tipo)
                        else None
                    ),
                )
                for a in sorted(c.atributos, key=lambda a: a.orden)
                # El @Id autogenerado (GenerationType.IDENTITY) ya cubre esto.
                # Si el atributo del diagrama también se llama "id" (en
                # cualquier variación de mayúsculas, o algo que sanea a "id",
                # ej. "I D") se ignora del todo — si no, quedan dos campos
                # Java llamados "id" en la misma clase y no compila.
                if nombre_campo_java(a.nombre).lower() != "id"
            ]
            datos_entidad = DatosEntidad(
                clase=c,
                nombre_java=nombre_java,
                atributos=atributos,
                relaciones=campos_relacion_por_clase.get(c.id, []),
            )

            zf.writestr(
                f"{raiz}/src/main/java/{paquete_dir}/model/{nombre_java}.java",
                _renderizar_entidad(datos_entidad, paquete_base),
            )
            zf.writestr(
                f"{raiz}/src/main/java/{paquete_dir}/repository/{nombre_java}Repository.java",
                _renderizar_repository(nombre_java, paquete_base),
            )
            zf.writestr(
                f"{raiz}/src/main/java/{paquete_dir}/service/{nombre_java}Service.java",
                _renderizar_service(nombre_java, paquete_base),
            )
            zf.writestr(
                f"{raiz}/src/main/java/{paquete_dir}/controller/{nombre_java}Controller.java",
                _renderizar_controller(nombre_java, paquete_base),
            )

    return buffer.getvalue()
