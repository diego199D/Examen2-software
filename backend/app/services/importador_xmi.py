"""
Importador de XMI 2.x/UML2 hacia el diagrama de clases de un proyecto (CU09
— complementa la exportación de `app/services/generador_xmi.py`, CU07).

Interpreta los mismos elementos que produce `generador_xmi.py`
(`uml:Class`, `ownedAttribute`, `generalization`, `uml:Association` con
`ownedEnd`/`aggregation`), pero **no asume que el archivo viene de nuestro
propio exportador** — un XMI real de Enterprise Architect (u otra
herramienta) puede declarar el namespace de XMI/UML con otra URI (2.4, 2.5.1,
...), anidar las clases dentro de `uml:Package`, referenciar el tipo de un
atributo con un `uml:PrimitiveType`/`uml:DataType` propio declarado en el
mismo documento (en vez del `href` externo que usamos nosotros), u omitir
`memberEnd` confiando solo en el anidamiento de `ownedEnd`. Ver la sección
"Tolerancia" más abajo para el detalle de qué variaciones se soportan.

--------------------------------------------------------------------------
Regla de alcance (impuesta por el router, no por este módulo)
--------------------------------------------------------------------------
Este módulo solo PARSEA y construye un `DiagramaIO` en memoria — no toca la
base de datos ni decide si el proyecto puede recibir la importación. La
regla "solo se importa sobre un diagrama vacío" vive en
`app/routers/diagramas.py` (409 si el proyecto ya tiene clases), y la
escritura reutiliza `app/services/diagrama.py::guardar_diagrama` (la misma
función que ya usa el autoguardado de CU09) — no se duplica esa lógica acá.

--------------------------------------------------------------------------
Tolerancia: qué variaciones del estándar se tratan de interpretar
--------------------------------------------------------------------------
- **Namespace de XMI/UML con otra URI o prefijo**: todo el matching es por
  NOMBRE LOCAL (`Class`, `Property`, `Association`, `Generalization` como
  valor de `xmi:type`; `id`/`type`/`name`/... como nombre de atributo),
  ignorando a propósito con qué URI/prefijo esté declarado el namespace —
  XMI 2.1/2.4/2.5.1 usan URIs distintas para lo mismo. Ver `_local`/`_attr`.
- **Clases anidadas en `uml:Package`** (no solo `packagedElement` directo
  del `uml:Model`): se busca en todo el árbol (`_elementos_del_modelo`),
  no solo entre los hijos directos del modelo -- SALTEANDO los bloques
  `xmi:Extension` (datos propios de cada herramienta, no modelo).
- **Probado contra un archivo REAL exportado por Enterprise Architect**
  (`tests/fixtures/ea_pedidos.xmi`, 2026-09-22) -- encontró dos bugs que los
  XMI "estilo EA" escritos a mano no mostraban: (1) EA repite cada clase
  dentro de su `xmi:Extension` (`<element xmi:idref=... xmi:type="uml:Class"
  name=...>`), así que se importaba cada una dos veces y el guardado daba
  409 por nombre duplicado; (2) EA escribe las referencias como HIJOS con
  `xmi:idref` (`<type xmi:idref="X"/>`, `<memberEnd xmi:idref="X"/>`,
  `<general xmi:idref="X"/>`) en vez de atributos planos -- las asociaciones
  se descartaban todas. Ver `_elementos_del_modelo` y `_referencia`.
- **Tipo de atributo como referencia interna** (`type="EAID_xxx"` apuntando
  a un `uml:PrimitiveType`/`uml:DataType` declarado en el mismo documento,
  el estilo típico de Enterprise Architect) además del `<type href="...#Foo"/>`
  externo que usa nuestro propio exportador — se prueban ambos.
- **`memberEnd` ausente en la Asociación**: si no están los dos ids, se cae
  a buscar los `ownedEnd` anidados directamente.
- **Generalización "suelta"** (no anidada dentro de la subclase, con
  `specific`/`general` como atributos en vez de depender del anidamiento):
  se resuelve `specific` por atributo si está, si no por el padre real del
  elemento en el árbol.
- **Multiplicidad no representable exactamente** en las 4 opciones que
  soporta este diagramador (`1`, `0..1`, `0..*`, `1..*`) — ej. un XMI
  externo con `2..5` — se aproxima al bucket más cercano (ver
  `_normalizar_multiplicidad`) y se dejan advertencias, en vez de rechazar
  todo el archivo por un valor que no tiene equivalente exacto.

--------------------------------------------------------------------------
Qué NO se interpreta (se reporta como advertencia, no como error fatal)
--------------------------------------------------------------------------
- **Clases u atributos sin `name`**: se omiten (no se inventa un nombre) y
  se deja una advertencia — un elemento sin nombre no se puede representar
  como `ClaseUml`/`Atributo` (ambos exigen nombre no vacío).
- **`ownedOperation` (métodos)**: no se importan — mismo criterio que ya
  documentan CU07/CU08/CU15 (no se generan/exportan métodos, `parametros`
  es texto libre sin estructura). Se deja una advertencia por clase que
  tenía operaciones en el archivo, para que quede claro que se perdieron.
- **Tipo de atributo que no se pudo resolver** (referencia rota, o a algo
  fuera del documento): el atributo se importa igual, sin tipo (`tipo=None`,
  el mismo estado que "no especificado" al modelar a mano), con advertencia.
- **Extremos de asociación / generalización que referencian una clase no
  encontrada** (payload roto, referencia externa al documento, o la clase
  referenciada se omitió por no tener nombre): la relación completa se
  descarta, con advertencia — no se arma una relación "a medias".
- **Estereotipos**: no se intenta recuperar `estereotipo` desde el
  `ownedComment` informativo que deja nuestro propio exportador (ver
  `generador_xmi.py`) — parsear una oración en lenguaje libre para
  reconstruir un campo estructurado es frágil y, peor, acoplaría este
  importador "tolerante" a la redacción exacta de nuestro propio texto,
  justo lo que se busca evitar. Las clases importadas nunca traen
  estereotipo, venga el archivo de donde venga.
- **Todo lo demás del archivo** (información de diagrama/layout,
  `xmi:Extension` propietario de una herramienta, perfiles/estereotipos
  UML formales, diagramas que no son de clases) se ignora sin advertencia
  — no es información que este diagramador modele en absoluto, no es un
  caso de "no se pudo interpretar" sino de "no aplica".
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from app.models.atributo import VisibilidadMiembro
from app.models.relacion import TipoRelacion
from app.schemas.diagrama import AtributoIO, ClaseIO, DiagramaIO, RelacionIO


class XmiInvalidoError(Exception):
    """El archivo no se puede interpretar en absoluto: ni es XML válido, ni
    contiene ninguna clase UML reconocible. El router lo traduce a 400."""


@dataclass
class ResultadoImportacionXmi:
    diagrama: DiagramaIO
    advertencias: list[str] = field(default_factory=list)


_VISIBILIDAD_DESDE_XMI: dict[str, VisibilidadMiembro] = {
    "public": VisibilidadMiembro.PUBLICO,
    "private": VisibilidadMiembro.PRIVADO,
    "protected": VisibilidadMiembro.PROTEGIDO,
    "package": VisibilidadMiembro.PAQUETE,
}

_AGGREGATION_A_TIPO: dict[str, TipoRelacion] = {
    "shared": TipoRelacion.AGREGACION,
    "composite": TipoRelacion.COMPOSICION,
}

# multiplicidad exacta (lower, upper) -> una de las 4 que soporta el diagramador.
_MULTIPLICIDAD_EXACTA: dict[tuple[str, str], str] = {
    ("1", "1"): "1",
    ("0", "1"): "0..1",
    ("0", "*"): "0..*",
    ("1", "*"): "1..*",
}

# El XMI no trae posición (ver "layout/UMLDI" en las limitaciones de CU07) --
# se ubican en la misma grilla que usa el frontend para "Nueva clase"
# (GRID_COLUMNAS/GRID_PASO_X/GRID_PASO_Y en useDiagrama.ts) en vez de
# amontonarlas todas en (0, 0), que sería inutilizable hasta reacomodarlas
# a mano una por una.
_GRID_COLUMNAS = 4
_GRID_PASO_X = 240
_GRID_PASO_Y = 180


def _posicion_en_grilla(indice: int) -> tuple[float, float]:
    columna = indice % _GRID_COLUMNAS
    fila = indice // _GRID_COLUMNAS
    return 80 + columna * _GRID_PASO_X, 80 + fila * _GRID_PASO_Y


def _local(nombre: str) -> str:
    """Nombre local de un tag o clave de atributo de ElementTree, sin
    importar el namespace (`{uri}local` -> `local`)."""
    return nombre.rsplit("}", 1)[-1]


def _attr_xmi(el: ET.Element, nombre_local: str) -> str | None:
    """Valor de un atributo NAMESPACED de `el` (`xmi:id`, `xmi:type`,
    `xmi:idref`) buscado por nombre local, sin importar con qué URI/prefijo
    esté declarado el namespace xmi en el archivo real (2.1 vs 2.4 vs
    2.5.1...). Restringido a claves namespaced a propósito: un atributo
    PLANO como `type` (la referencia IDREF al tipo de una Property) tiene el
    mismo nombre local que `xmi:type` (la metaclase) pero son cosas
    completamente distintas -- confundirlos rompe la resolución de
    referencias (ver `_attr` para los planos)."""
    for clave, valor in el.attrib.items():
        if clave.startswith("{") and _local(clave) == nombre_local:
            return valor
    return None


def _attr(el: ET.Element, *nombres_locales: str) -> str | None:
    """Valor de un atributo PLANO (sin namespace) de `el` -- `name`, `type`
    (IDREF), `general`, `specific`, `aggregation`, `association`,
    `visibility`, `isAbstract`, `memberEnd`, `value`, `href`... Así es como
    XMI serializa estos (nunca namespaced), a diferencia de `xmi:id`/
    `xmi:type` -- ver `_attr_xmi`."""
    for clave, valor in el.attrib.items():
        if not clave.startswith("{") and clave in nombres_locales:
            return valor
    return None


def _tipo_xmi_local(el: ET.Element) -> str | None:
    """El valor de `xmi:type` de `el` sin el prefijo (`uml:Class` -> `Class`)."""
    valor = _attr_xmi(el, "type")
    if valor is None:
        return None
    return valor.rsplit(":", 1)[-1]


def _elementos_del_modelo(root: ET.Element):
    """Como `root.iter()`, pero salteando todo subárbol `xmi:Extension`: es
    el mecanismo estándar de XMI para datos PROPIOS de cada herramienta, no
    parte del modelo. Enterprise Architect repite ahí cada clase
    (`<element xmi:idref=... xmi:type="uml:Class" name=...>`, con datos de
    dibujo) -- recorrerlo importaba cada clase dos veces (bug real, con un
    archivo exportado por EA). OJO: el índice de ids (`importar_xmi`) sí
    recorre el documento entero, porque EA declara ahí dentro los
    `PrimitiveType` a los que apuntan los tipos de los atributos."""
    pendientes = [root]
    while pendientes:
        el = pendientes.pop()
        if _local(el.tag) == "Extension":
            continue
        yield el
        pendientes.extend(reversed(list(el)))


def _referencia(el: ET.Element, nombre_local: str) -> str | None:
    """Una referencia IDREF que XMI permite escribir de dos formas: como
    atributo plano (`type="X"`, estilo de nuestro exportador) o como hijo
    con `xmi:idref` (`<type xmi:idref="X"/>`, estilo de Enterprise
    Architect). Antes solo se leía la primera y todas las asociaciones de
    un archivo de EA se descartaban."""
    valor = _attr(el, nombre_local)
    if valor:
        return valor
    for hijo in _hijos(el, nombre_local):
        idref = _attr_xmi(hijo, "idref")
        if idref:
            return idref
    return None


def _hijos(el: ET.Element, nombre_local: str) -> list[ET.Element]:
    """Hijos DIRECTOS de `el` cuyo tag (nombre de rol de contención, ej.
    `ownedAttribute`) coincide por nombre local, sin importar namespace."""
    return [hijo for hijo in el if _local(hijo.tag) == nombre_local]


def _valor_hijo(el: ET.Element, nombre_local: str) -> str | None:
    """El atributo `value` del primer hijo de `el` con ese nombre local
    (para `lowerValue`/`upperValue`), o `None` si no existe."""
    hijos = _hijos(el, nombre_local)
    return hijos[0].get("value") if hijos else None


def _normalizar_multiplicidad(lower: str | None, upper: str | None) -> tuple[str | None, bool]:
    """(multiplicidad soportada o `None`, si tuvo que aproximarse). `None`
    cuando el XMI no traía nada de multiplicidad para ese extremo (mismo
    estado que "no especificado" al modelar a mano)."""
    if lower is None and upper is None:
        return None, False

    l = lower if lower is not None else "1"
    u = upper if upper is not None else l
    if u in ("*", "-1", "unbounded", "unlimited"):
        u = "*"

    exacta = _MULTIPLICIDAD_EXACTA.get((l, u))
    if exacta is not None:
        return exacta, False

    try:
        l_num = int(l)
    except ValueError:
        l_num = 0

    if u == "*":
        return ("0..*" if l_num == 0 else "1..*"), True

    try:
        u_num = int(u)
    except ValueError:
        u_num = 1
    if u_num <= 1:
        return ("0..1" if l_num == 0 else "1"), True
    return ("0..*" if l_num == 0 else "1..*"), True


def _resolver_tipo_atributo(
    attr_el: ET.Element, indice_por_id: dict[str, ET.Element], advertencias: list[str], contexto: str
) -> str | None:
    """Intenta, en orden: (1) `<type href="...#Foo"/>` externo (lo que usa
    nuestro propio exportador), (2) `<type>`/atributo `type` como IDREF a un
    elemento del mismo documento (el estilo típico de Enterprise Architect,
    que declara sus propios `PrimitiveType`/`DataType` localmente) — de ese
    elemento se toma su `name`. Si había una referencia pero no se pudo
    resolver, deja una advertencia y devuelve `None` en vez de inventar
    un tipo o fallar todo el archivo."""
    tipo_el = next(iter(_hijos(attr_el, "type")), None)
    href = tipo_el.get("href") if tipo_el is not None else None
    if href:
        fragmento = href.rsplit("#", 1)[-1].strip()
        if fragmento:
            return fragmento

    idref = _attr_xmi(tipo_el, "idref") if tipo_el is not None else None
    if idref is None:
        idref = _attr(attr_el, "type")

    if idref:
        referenciado = indice_por_id.get(idref)
        if referenciado is not None and referenciado.get("name"):
            return referenciado.get("name")
        advertencias.append(
            f'{contexto}: el tipo referenciado ("{idref}") no se pudo resolver dentro del archivo '
            "-- se importó sin tipo especificado."
        )
        return None

    return None


def _parsear_clases(
    root: ET.Element, indice_por_id: dict[str, ET.Element], advertencias: list[str]
) -> tuple[list[ClaseIO], dict[str, str]]:
    """Devuelve las clases parseadas y el mapeo `xmi:id externo -> id
    interno nuevo`. Los ids del archivo NUNCA se reusan tal cual como
    `ClaseUml.id`: son texto arbitrario de una herramienta externa y
    `clases_uml.id` es una clave primaria GLOBAL (no compuesta con
    `id_proyecto`) -- reusarlos podría chocar con clases de otro proyecto
    cualquiera en la misma base de datos."""
    clases: list[ClaseIO] = []
    id_externo_a_interno: dict[str, str] = {}

    for clase_el in _elementos_del_modelo(root):
        if _tipo_xmi_local(clase_el) != "Class":
            continue
        # Una referencia a una clase (solo `xmi:idref`, sin `xmi:id`) no es
        # su definición -- segunda defensa además de saltear xmi:Extension.
        if _attr_xmi(clase_el, "id") is None and _attr_xmi(clase_el, "idref") is not None:
            continue

        nombre = (clase_el.get("name") or "").strip()
        xid_externo = _attr_xmi(clase_el, "id")
        if not nombre:
            advertencias.append(f'Se omitió una clase sin nombre (xmi:id="{xid_externo}").')
            continue

        nuevo_id = str(uuid.uuid4())
        if xid_externo:
            id_externo_a_interno[xid_externo] = nuevo_id

        atributos: list[AtributoIO] = []
        for orden, attr_el in enumerate(_hijos(clase_el, "ownedAttribute")):
            nombre_attr = (attr_el.get("name") or "").strip()
            if not nombre_attr:
                advertencias.append(f'Clase "{nombre}": se omitió un atributo sin nombre.')
                continue
            tipo = _resolver_tipo_atributo(
                attr_el, indice_por_id, advertencias, f'Clase "{nombre}", atributo "{nombre_attr}"'
            )
            visibilidad = _VISIBILIDAD_DESDE_XMI.get(
                (_attr(attr_el, "visibility") or "").lower(), VisibilidadMiembro.PRIVADO
            )
            atributos.append(
                AtributoIO(id=str(uuid.uuid4()), nombre=nombre_attr, tipo=tipo, visibilidad=visibilidad, orden=orden)
            )

        operaciones = _hijos(clase_el, "ownedOperation")
        if operaciones:
            advertencias.append(
                f'Clase "{nombre}": tiene {len(operaciones)} método(s) en el archivo XMI -- '
                "los métodos no se importan (misma limitación que la exportación)."
            )

        pos_x, pos_y = _posicion_en_grilla(len(clases))
        clases.append(
            ClaseIO(
                id=nuevo_id,
                nombre=nombre,
                estereotipo=None,  # ver "Qué NO se interpreta" en el encabezado del módulo
                es_abstracta=(_attr(clase_el, "isAbstract") or "").lower() in ("true", "1"),
                pos_x=pos_x,
                pos_y=pos_y,
                atributos=atributos,
            )
        )

    return clases, id_externo_a_interno


def _parsear_generalizaciones(
    root: ET.Element, id_externo_a_interno: dict[str, str], advertencias: list[str]
) -> list[RelacionIO]:
    padre_de: dict[ET.Element, ET.Element] = {
        hijo: padre for padre in _elementos_del_modelo(root) for hijo in padre
    }
    relaciones: list[RelacionIO] = []

    for gen_el in _elementos_del_modelo(root):
        if _tipo_xmi_local(gen_el) != "Generalization":
            continue

        general_ext = _referencia(gen_el, "general")
        specific_ext = _referencia(gen_el, "specific")
        if specific_ext is None:
            padre = padre_de.get(gen_el)
            specific_ext = _attr_xmi(padre, "id") if padre is not None else None

        origen = id_externo_a_interno.get(specific_ext) if specific_ext else None
        destino = id_externo_a_interno.get(general_ext) if general_ext else None
        if origen is None or destino is None:
            advertencias.append(
                "Se omitió una generalización (herencia) que referencia una clase no reconocida en el archivo "
                f'(specific="{specific_ext}", general="{general_ext}").'
            )
            continue

        relaciones.append(
            RelacionIO(
                id=str(uuid.uuid4()),
                id_clase_origen=origen,
                id_clase_destino=destino,
                tipo=TipoRelacion.HERENCIA,
            )
        )

    return relaciones


def _parsear_asociaciones(
    root: ET.Element, id_externo_a_interno: dict[str, str], advertencias: list[str]
) -> list[RelacionIO]:
    propiedades_por_id: dict[str, ET.Element] = {}
    for el in _elementos_del_modelo(root):
        if _tipo_xmi_local(el) == "Property":
            xid = _attr_xmi(el, "id")
            if xid:
                propiedades_por_id[xid] = el

    relaciones: list[RelacionIO] = []

    for assoc_el in _elementos_del_modelo(root):
        if _tipo_xmi_local(assoc_el) != "Association":
            continue

        nombre_assoc = assoc_el.get("name")
        # memberEnd puede venir como atributo con ids separados por espacios
        # (nuestro exportador) o como hijos `<memberEnd xmi:idref=.../>` (EA).
        ids_member_end = (_attr(assoc_el, "memberEnd") or "").split() + [
            idref for hijo in _hijos(assoc_el, "memberEnd") if (idref := _attr_xmi(hijo, "idref"))
        ]
        extremos: list[ET.Element] = []
        for xid in dict.fromkeys(ids_member_end):  # sin repetidos, conservando el orden
            prop = propiedades_por_id.get(xid)
            if prop is not None:
                extremos.append(prop)
        if not extremos:
            extremos = _hijos(assoc_el, "ownedEnd")

        if len(extremos) < 2:
            advertencias.append(
                f'Se omitió la asociación "{nombre_assoc or assoc_el.get("id", "(sin nombre)")}": '
                "no se pudieron resolver sus dos extremos en el archivo."
            )
            continue
        if len(extremos) > 2:
            advertencias.append(
                f'La asociación "{nombre_assoc or "(sin nombre)"}" tiene más de dos extremos (n-aria) -- '
                "este diagramador solo soporta relaciones binarias, se usaron los dos primeros."
            )
        extremo_a, extremo_b = extremos[0], extremos[1]

        tipo_a = _referencia(extremo_a, "type")
        tipo_b = _referencia(extremo_b, "type")
        clase_a = id_externo_a_interno.get(tipo_a) if tipo_a else None
        clase_b = id_externo_a_interno.get(tipo_b) if tipo_b else None
        if clase_a is None or clase_b is None:
            advertencias.append(
                f'Se omitió la asociación "{nombre_assoc or "(sin nombre)"}": uno de sus extremos '
                "referencia una clase no reconocida en el archivo."
            )
            continue

        aggregation_a = (_attr(extremo_a, "aggregation") or "none").lower()
        aggregation_b = (_attr(extremo_b, "aggregation") or "none").lower()
        # El extremo con aggregation "shared"/"composite" es la PARTE -> en
        # nuestro modelo esa clase va del lado `destino` (mismo criterio que
        # usa generador_xmi.py al exportar, ver su encabezado). Si ninguno
        # de los dos trae aggregation, o (caso irregular) los dos la traen,
        # se conserva el orden tal cual aparece en el archivo.
        if aggregation_a in _AGGREGATION_A_TIPO and aggregation_b not in _AGGREGATION_A_TIPO:
            origen_el, destino_el = extremo_b, extremo_a
            origen_id, destino_id = clase_b, clase_a
            tipo_relacion = _AGGREGATION_A_TIPO[aggregation_a]
        elif aggregation_b in _AGGREGATION_A_TIPO:
            origen_el, destino_el = extremo_a, extremo_b
            origen_id, destino_id = clase_a, clase_b
            tipo_relacion = _AGGREGATION_A_TIPO[aggregation_b]
        else:
            origen_el, destino_el = extremo_a, extremo_b
            origen_id, destino_id = clase_a, clase_b
            tipo_relacion = TipoRelacion.ASOCIACION

        lower_o = _valor_hijo(origen_el, "lowerValue") or _attr(origen_el, "lower")
        upper_o = _valor_hijo(origen_el, "upperValue") or _attr(origen_el, "upper")
        lower_d = _valor_hijo(destino_el, "lowerValue") or _attr(destino_el, "lower")
        upper_d = _valor_hijo(destino_el, "upperValue") or _attr(destino_el, "upper")
        mult_origen, aprox_o = _normalizar_multiplicidad(lower_o, upper_o)
        mult_destino, aprox_d = _normalizar_multiplicidad(lower_d, upper_d)
        if aprox_o or aprox_d:
            advertencias.append(
                f'Asociación "{nombre_assoc or "(sin nombre)"}": la multiplicidad de uno de sus extremos '
                f"no tiene equivalente exacto entre 1/0..1/0..*/1..* -- se aproximó "
                f"(origen={mult_origen}, destino={mult_destino})."
            )

        relaciones.append(
            RelacionIO(
                id=str(uuid.uuid4()),
                id_clase_origen=origen_id,
                id_clase_destino=destino_id,
                tipo=tipo_relacion,
                etiqueta=nombre_assoc,
                multiplicidad_origen=mult_origen,
                multiplicidad_destino=mult_destino,
            )
        )

    return relaciones


def importar_xmi(contenido: bytes) -> ResultadoImportacionXmi:
    """Parsea `contenido` (bytes crudos de un archivo `.xmi`) y arma el
    `DiagramaIO` correspondiente. Levanta `XmiInvalidoError` si el archivo
    no es XML válido o no contiene ninguna clase UML reconocible -- el
    router lo traduce a 400. Cualquier otra cosa que no se haya podido
    interpretar del todo queda como advertencia en el resultado, no como
    error fatal (ver "Tolerancia" en el encabezado del módulo)."""
    try:
        root = ET.fromstring(contenido)
    except ET.ParseError as err:
        raise XmiInvalidoError(f"El archivo no es XML válido: {err}") from err

    advertencias: list[str] = []
    indice_por_id: dict[str, ET.Element] = {}
    for el in root.iter():
        xid = _attr_xmi(el, "id")
        if xid:
            indice_por_id[xid] = el

    clases, id_externo_a_interno = _parsear_clases(root, indice_por_id, advertencias)
    if not clases:
        raise XmiInvalidoError(
            "El archivo no contiene ninguna clase UML (uml:Class) reconocible con nombre."
        )

    relaciones = _parsear_generalizaciones(root, id_externo_a_interno, advertencias)
    relaciones += _parsear_asociaciones(root, id_externo_a_interno, advertencias)

    return ResultadoImportacionXmi(
        diagrama=DiagramaIO(clases=clases, relaciones=relaciones),
        advertencias=advertencias,
    )
