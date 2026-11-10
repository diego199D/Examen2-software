"""
Generador de exportación XMI 2.1 / UML 2.x del diagrama de clases de un
proyecto (CU07 — tercer formato de reporte, junto a PDF e Imagen).

Formato elegido: **XMI 2.1** con los namespaces canónicos de la OMG
(`http://schema.omg.org/spec/XMI/2.1` y `http://schema.omg.org/spec/UML/2.1`),
el mismo par de namespaces que usa Enterprise Architect (EA) tanto al
exportar como al aceptar un XMI de otra herramienta — confirmado leyendo un
XMI 2.1 real exportado por EA (repositorio público de ejemplos), no
solo por la especificación. La estructura de elementos (`packagedElement`,
`ownedAttribute`, `ownedEnd`, `generalization`, `lowerValue`/`upperValue`)
sigue el patrón estándar de serialización XMI para el metamodelo UML2:
el NOMBRE del tag es el rol/propiedad de contención (sin prefijo), y el
METACLASE real se indica con el atributo `xmi:type="uml:Xxx"` — así es como
lucen los XMI reales de EA, ArgoUML, Papyrus, StarUML, etc.

**Verificado por la usuaria en una instalación real de Enterprise
Architect** (2026-09-22): el archivo exportado se abre en EA y reconoce
clases, atributos y relaciones del modelo. EA no crea el diagrama dibujado
(el XMI no lleva layout, ver limitaciones al final del archivo): hay que
arrastrar las clases al lienzo, y las relaciones aparecen solas. Se decidió
dejarlo así. El mismo diagrama, re-exportado desde EA, es el fixture real
del importador (`tests/fixtures/ea_pedidos.xmi`).

Reutiliza `app/services/diagrama.py::cargar_clases_y_relaciones` — la misma
lectura de `clases_uml`/`relaciones` que ya usan `generador_spring.py` (CU08)
y `generador_flutter.py` (CU15) — no se duplica la consulta.

--------------------------------------------------------------------------
Mapeo de conceptos del diagrama a elementos XMI/UML 2.x
--------------------------------------------------------------------------
- `ClaseUml`              -> `packagedElement` `xmi:type="uml:Class"`.
- `Atributo`              -> `ownedAttribute` `xmi:type="uml:Property"`
                             (tipo mapeado a un primitivo UML estándar, ver
                             `MAPEO_TIPOS_XMI`).
- `Relacion` HERENCIA     -> `generalization` `xmi:type="uml:Generalization"`,
                             anidado dentro del `packagedElement` de la clase
                             ORIGEN (la subclase) — así lo exige el metamodelo:
                             `Generalization` no es un `PackageableElement`,
                             no puede ir suelto como `packagedElement`, tiene
                             que colgar de `Classifier::generalization` de la
                             clase específica. `id_clase_origen` = subclase,
                             `id_clase_destino` = superclase (misma
                             convención que ya usa el marcador visual de la
                             flecha en el lienzo, ver `markerDeRelacion` en
                             el frontend).
- `Relacion` ASOCIACION/
  AGREGACION/COMPOSICION  -> `packagedElement` `xmi:type="uml:Association"`
                             con dos `ownedEnd` (`xmi:type="uml:Property"`),
                             uno tipado con la clase origen y otro con la
                             clase destino. La multiplicidad de cada extremo
                             sale de `multiplicidad_origen`/`multiplicidad_destino`
                             (mismo criterio que ya usa `generador_reporte.py`:
                             la multiplicidad escrita "en" un extremo describe
                             cuántas instancias de ESA clase participan por
                             cada instancia del otro extremo).
                             Para AGREGACION/COMPOSICION, el atributo
                             `aggregation` ("shared"/"composite") se coloca en
                             el extremo tipado con la clase PARTE (destino) —
                             es la convención estándar del metamodelo UML2
                             (el rombo se dibuja del lado del "todo", pero el
                             `AggregationKind` es una propiedad del extremo
                             cuyo tipo ES la parte), confirmada además contra
                             ejemplos públicos de asociaciones compuestas en
                             XMI. Coincide con la convención ya usada en el
                             lienzo: `id_clase_origen` = todo (el rombo sale
                             de ahí, ver `markerStart` en `umlFormat.ts`),
                             `id_clase_destino` = parte.

--------------------------------------------------------------------------
Qué del estándar XMI/UML 2.x completo NO se cubre (documentado a propósito)
--------------------------------------------------------------------------
- **Solo diagrama de clases.** No se exportan otros tipos de diagrama UML
  (secuencia, actividades, casos de uso, etc.) — el diagramador solo modela
  clases, así que no hay nada de eso que exportar; no es una limitación del
  generador sino del alcance de la herramienta.
- **Sin información visual/de diagrama** (`uml:Diagram`, geometría de nodos,
  posición `pos_x`/`pos_y`, estilos de línea). El XMI exportado es el MODELO
  (clases/atributos/relaciones), no el DIAGRAMA (layout visual) — es la
  distinción estándar entre `UML` y `UMLDI` (UML Diagram Interchange) de la
  propia OMG. Herramientas como EA sí pueden reconstruir un diagrama a partir
  del modelo importado (auto-layout), pero no van a respetar las posiciones
  que tenía en este editor.
- **Estereotipos** (`ClaseUml.estereotipo`, texto libre en este diagramador)
  no se traducen a un `Stereotype` UML formal — eso exige definir y aplicar
  un `Profile` UML (un mecanismo de extensión completo, con su propio
  paquete y metaclases extendidas), que excede por mucho lo que pide este
  campo de texto libre. En vez de perder la información en silencio, cada
  clase con estereotipo lleva un `ownedComment` con el texto original
  (ej. `Estereotipo original del diagrama: «entity»`), legible al abrir el
  archivo pero sin la semántica formal de un Stereotype aplicado.
- **Métodos** (`Metodo`) no se exportan como `ownedOperation`. `parametros`
  es texto libre sin estructura (ej. `"id: int, nombre: String"`) — la ficha
  de CU07 no pidió parsear eso a `ownedParameter` individuales, y forzar un
  parser ad-hoc para texto arbitrario es fábrica de bugs silenciosos. Mismo
  criterio que ya usa CU08 (Spring Boot tampoco genera métodos desde el
  diagrama) — se documenta como limitación en vez de intentar un parseo
  frágil.
- **Navegabilidad formal** (`isNavigable`/`navigableOwnedEnd`) no se modela:
  ambos extremos de toda asociación se exportan como `ownedEnd` (no
  navegables por default en el metamodelo si no se listan aparte en
  `navigableOwnedEnd`). La flecha que se ve en el lienzo para ASOCIACION es
  un estilo visual del editor, no un dato de navegabilidad que el diagrama
  capture explícitamente por extremo.
- **Multiplicidad no especificada** (`None`, el usuario no la definió en el
  extremo) se exporta sin `lowerValue`/`upperValue` — el default del
  metamodelo UML2 para una `Property` sin esos elementos es `1..1`, que es
  lo más parecido a "no especificado" sin inventar un valor que el usuario
  no puso.
- **Tipos de atributo sin equivalente primitivo en UML** (`date`, `datetime`,
  `uuid`, o cualquier tipo no reconocido/typo): la librería estándar de
  tipos primitivos de UML2 (`PrimitiveTypes`) solo define `String`, `Integer`,
  `Boolean`, `Real` y `UnlimitedNatural` — no hay un primitivo `Date` ni
  `UUID`. Se mapean a `String` (mismo criterio de "default seguro + aviso
  visible" que `generador_spring.py`/`generador_flutter.py`): un
  `ownedComment` en el atributo deja constancia del tipo original del
  diagrama cuando no hay mapeo directo.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.models.atributo import Atributo
from app.models.clase_uml import ClaseUml
from app.models.proyecto import Proyecto
from app.models.relacion import Relacion, TipoRelacion

XMI_NS = "http://schema.omg.org/spec/XMI/2.1"
UML_NS = "http://schema.omg.org/spec/UML/2.1"
# Namespace de la librería estándar de tipos primitivos UML2 — se referencia
# por `href` (cross-document) en vez de declarar un `uml:PrimitiveType`
# propio con un id inventado: es la forma portable/estándar de referenciar
# los primitivos de la OMG en vez de depender de ids internos de una
# herramienta puntual (EA, por ejemplo, usa sus propios GUIDs opacos para
# esto en su copia interna de la librería).
_PRIMITIVE_TYPES_HREF = "http://schema.omg.org/spec/UML/2.1/uml.xml#{}"

ET.register_namespace("xmi", XMI_NS)
ET.register_namespace("uml", UML_NS)


def _xmi(nombre: str) -> str:
    return f"{{{XMI_NS}}}{nombre}"


# --------------------------------------------------------------------------
# Mapeo de tipos UML del diagrama (texto libre) a los primitivos estándar de
# UML2 (`PrimitiveTypes`: String, Integer, Boolean, Real, UnlimitedNatural).
# Mismo vocabulario de entrada que `MAPEO_TIPOS_JAVA`/`MAPEO_TIPOS_DART`
# (generador_spring.py/generador_flutter.py) para que "qué se reconoce como
# tipo válido" sea consistente entre los tres exportadores.
# --------------------------------------------------------------------------

MAPEO_TIPOS_XMI: dict[str, str] = {
    "string": "String",
    "str": "String",
    "texto": "String",
    "char": "String",
    "int": "Integer",
    "integer": "Integer",
    "entero": "Integer",
    "long": "Integer",
    "float": "Real",
    "double": "Real",
    "decimal": "Real",
    "bigdecimal": "Real",
    "real": "Real",
    "boolean": "Boolean",
    "bool": "Boolean",
    # UML2 no tiene un primitivo Date/DateTime/UUID -- ver limitaciones en el
    # encabezado del módulo.
    "date": "String",
    "fecha": "String",
    "datetime": "String",
    "fechahora": "String",
    "timestamp": "String",
    "uuid": "String",
}
TIPO_XMI_POR_DEFECTO = "String"

_VISIBILIDAD_XMI = {
    "PUBLICO": "public",
    "PRIVADO": "private",
    "PROTEGIDO": "protected",
    "PAQUETE": "package",
}

_AGGREGATION_XMI = {
    TipoRelacion.AGREGACION: "shared",
    TipoRelacion.COMPOSICION: "composite",
}


def mapear_tipo_xmi(tipo_uml: str | None) -> str:
    if not tipo_uml:
        return TIPO_XMI_POR_DEFECTO
    return MAPEO_TIPOS_XMI.get(tipo_uml.strip().lower(), TIPO_XMI_POR_DEFECTO)


def tipo_no_reconocido(tipo_uml: str | None) -> bool:
    """True si se escribió un tipo que no está en `MAPEO_TIPOS_XMI` (typo,
    tipo custom, o un tipo sin primitivo UML2 equivalente como `date`) —
    mismo criterio que su equivalente en generador_spring.py/generador_flutter.py:
    no especificar tipo (`None`/vacío) no cuenta como "no reconocido"."""
    return bool(tipo_uml) and tipo_uml.strip().lower() not in MAPEO_TIPOS_XMI


def _lower_upper(multiplicidad: str | None) -> tuple[str, str] | None:
    """`None` si no hay multiplicidad especificada (se omite lowerValue/
    upperValue del todo, ver limitación documentada arriba). Los 4 valores
    vienen ya validados al guardar el diagrama (`MULTIPLICIDADES_VALIDAS` en
    `app/services/diagrama.py`), así que no hace falta un `else` defensivo."""
    return {
        "1": ("1", "1"),
        "0..1": ("0", "1"),
        "0..*": ("0", "*"),
        "1..*": ("1", "*"),
    }.get(multiplicidad)


def _agregar_tipo_primitivo(padre: ET.Element, tipo_xmi: str) -> None:
    tipo_el = ET.SubElement(padre, "type")
    tipo_el.set(_xmi("type"), "uml:PrimitiveType")
    tipo_el.set("href", _PRIMITIVE_TYPES_HREF.format(tipo_xmi))


def _agregar_comentario(padre: ET.Element, xmi_id: str, texto: str) -> None:
    comentario = ET.SubElement(padre, "ownedComment")
    comentario.set(_xmi("type"), "uml:Comment")
    comentario.set(_xmi("id"), xmi_id)
    comentario.set("body", texto)


def _agregar_atributo(clase_el: ET.Element, atributo: Atributo) -> None:
    attr_id = f"attr_{atributo.id}"
    attr_el = ET.SubElement(clase_el, "ownedAttribute")
    attr_el.set(_xmi("type"), "uml:Property")
    attr_el.set(_xmi("id"), attr_id)
    attr_el.set("name", atributo.nombre)
    visibilidad = _VISIBILIDAD_XMI.get(
        getattr(atributo.visibilidad, "value", atributo.visibilidad), "private"
    )
    attr_el.set("visibility", visibilidad)

    if tipo_no_reconocido(atributo.tipo):
        _agregar_comentario(
            attr_el,
            f"cmt_{atributo.id}",
            f'Tipo UML original del diagrama: "{atributo.tipo}" (sin primitivo UML2 '
            "equivalente, exportado como String)",
        )
    _agregar_tipo_primitivo(attr_el, mapear_tipo_xmi(atributo.tipo))


def _agregar_generalizacion(clase_el: ET.Element, relacion: Relacion) -> None:
    gen_el = ET.SubElement(clase_el, "generalization")
    gen_el.set(_xmi("type"), "uml:Generalization")
    gen_el.set(_xmi("id"), f"gen_{relacion.id}")
    gen_el.set("general", f"cls_{relacion.id_clase_destino}")


def _agregar_extremo(
    assoc_el: ET.Element,
    xmi_id: str,
    assoc_id: str,
    clase_id: str,
    multiplicidad: str | None,
    aggregation: str | None,
) -> ET.Element:
    end_el = ET.SubElement(assoc_el, "ownedEnd")
    end_el.set(_xmi("type"), "uml:Property")
    end_el.set(_xmi("id"), xmi_id)
    end_el.set("type", f"cls_{clase_id}")
    end_el.set("association", assoc_id)
    if aggregation:
        end_el.set("aggregation", aggregation)

    rango = _lower_upper(multiplicidad)
    if rango is not None:
        lower, upper = rango
        lower_el = ET.SubElement(end_el, "lowerValue")
        lower_el.set(_xmi("type"), "uml:LiteralInteger")
        lower_el.set("value", lower)
        upper_el = ET.SubElement(end_el, "upperValue")
        upper_el.set(_xmi("type"), "uml:LiteralUnlimitedNatural")
        upper_el.set("value", upper)
    return end_el


def _agregar_asociacion(modelo_el: ET.Element, relacion: Relacion) -> None:
    assoc_id = f"assoc_{relacion.id}"
    end_origen_id = f"end_origen_{relacion.id}"
    end_destino_id = f"end_destino_{relacion.id}"

    assoc_el = ET.SubElement(modelo_el, "packagedElement")
    assoc_el.set(_xmi("type"), "uml:Association")
    assoc_el.set(_xmi("id"), assoc_id)
    if relacion.etiqueta:
        assoc_el.set("name", relacion.etiqueta)
    assoc_el.set("memberEnd", f"{end_origen_id} {end_destino_id}")

    # El aggregation kind va en el extremo tipado con la clase PARTE
    # (destino) -- ver la explicación completa en el encabezado del módulo.
    aggregation_destino = _AGGREGATION_XMI.get(relacion.tipo)

    _agregar_extremo(
        assoc_el, end_origen_id, assoc_id, relacion.id_clase_origen, relacion.multiplicidad_origen, None
    )
    _agregar_extremo(
        assoc_el,
        end_destino_id,
        assoc_id,
        relacion.id_clase_destino,
        relacion.multiplicidad_destino,
        aggregation_destino,
    )


def generar_xmi_reporte(proyecto: Proyecto, clases: list[ClaseUml], relaciones: list[Relacion]) -> bytes:
    """Arma el archivo .xmi (UML2/XMI 2.1) del proyecto. Asume que `clases`
    no está vacío (el router ya valida el caso "sin contenido para
    exportar" antes de invocar esta función, igual que `generar_pdf_reporte`)."""
    xmi_root = ET.Element(_xmi("XMI"))
    xmi_root.set(_xmi("version"), "2.1")

    modelo_el = ET.SubElement(xmi_root, f"{{{UML_NS}}}Model")
    modelo_el.set(_xmi("type"), "uml:Model")
    modelo_el.set(_xmi("id"), "model_1")
    modelo_el.set("name", proyecto.nombre)

    clases_por_id = {c.id: c for c in clases}
    elementos_por_clase: dict[str, ET.Element] = {}

    for clase in sorted(clases, key=lambda c: c.nombre.lower()):
        clase_el = ET.SubElement(modelo_el, "packagedElement")
        clase_el.set(_xmi("type"), "uml:Class")
        clase_el.set(_xmi("id"), f"cls_{clase.id}")
        clase_el.set("name", clase.nombre)
        if clase.es_abstracta:
            clase_el.set("isAbstract", "true")
        elementos_por_clase[clase.id] = clase_el

        if clase.estereotipo:
            _agregar_comentario(
                clase_el,
                f"cmt_estereotipo_{clase.id}",
                f"Estereotipo original del diagrama: «{clase.estereotipo}» "
                "(no exportado como Stereotype UML formal, ver limitaciones del generador)",
            )

        for atributo in sorted(clase.atributos, key=lambda a: a.orden):
            _agregar_atributo(clase_el, atributo)

    for relacion in relaciones:
        if relacion.id_clase_origen not in clases_por_id or relacion.id_clase_destino not in clases_por_id:
            continue  # payload inconsistente -- ya se valida al guardar el diagrama (CU09)

        if relacion.tipo == TipoRelacion.HERENCIA:
            _agregar_generalizacion(elementos_por_clase[relacion.id_clase_origen], relacion)
        else:
            _agregar_asociacion(modelo_el, relacion)

    return ET.tostring(xmi_root, encoding="UTF-8", xml_declaration=True)
