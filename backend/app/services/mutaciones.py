"""
Segundo parcial (RF-IA-05/06) — herramienta `apply_diagram_mutations` del
Desarrollador Senior: aplica un LOTE de acciones sobre el diagrama de forma
atómica (o todo o nada).

Formato de una acción (ver también `ESQUEMA_HERRAMIENTA`, que es lo que ve
el modelo, con propiedades explícitas porque Gemini rechaza objetos sin
`properties`):

    {
      "action": "ADD_ENTITY" | "UPDATE_ENTITY" | "DELETE_ENTITY"
              | "ADD_ATTRIBUTE" | "UPDATE_ATTRIBUTE" | "DELETE_ATTRIBUTE"
              | "ADD_RELATIONSHIP" | "UPDATE_RELATIONSHIP" | "DELETE_RELATIONSHIP",
      "tempId": "t1",              # en ADD_*: id provisional para referenciarlo en el mismo lote
      "entityId": "...",           # id real, tempId o NOMBRE de la clase
      "attributeId": "...",        # id o nombre del atributo
      "relationshipId": "...",     # id real o tempId de la relación
      "entityData": {"name", "isAbstract", "stereotype", "attributes": [attributeData...]},
      "attributeData": {"name", "type", "visibility"},
      "relationshipData": {"sourceId", "targetId", "type", "sourceCardinality",
                           "targetCardinality", "label", "associationClassId"}
    }

`tempId` → id real: una relación puede apuntar a una clase creada en el
mismo lote (ej. crear `DetalleFactura` y relacionarla con `Factura`). Los
ids reales se generan acá (uuid4), igual que los genera el frontend.

Validación: ids/nombres existentes, tipos de atributo de una lista cerrada
(acepta sinónimos SQL: varchar, integer, numeric, timestamp...),
tipo de relación y cardinalidades del enum, y al final las mismas reglas
que el guardado normal (`validar_diagrama`: nombres de clase únicos, etc.).
Si cualquier acción falla, se lanza `MutacionInvalidaError` y el diagrama
original queda intacto.

Las clases nuevas se ubican en celdas libres de una grilla, sin encimarse
con ninguna clase existente (estimando su alto por cantidad de miembros).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException

from app.models.atributo import VisibilidadMiembro
from app.models.relacion import TipoRelacion
from app.schemas.diagrama import AtributoIO, ClaseIO, DiagramaIO, RelacionIO
from app.services.diagrama import MULTIPLICIDADES_VALIDAS, validar_diagrama
from app.services.nombres import normalizar_nombre

ACCIONES = [
    "ADD_ENTITY",
    "UPDATE_ENTITY",
    "DELETE_ENTITY",
    "ADD_ATTRIBUTE",
    "UPDATE_ATTRIBUTE",
    "DELETE_ATTRIBUTE",
    "ADD_RELATIONSHIP",
    "UPDATE_RELATIONSHIP",
    "DELETE_RELATIONSHIP",
]

# Tipo canónico (el que se guarda en el diagrama) por cada nombre aceptado.
TIPOS_ATRIBUTO: dict[str, str] = {
    "string": "String", "varchar": "String", "text": "String", "char": "String", "texto": "String",
    "int": "int", "integer": "int", "entero": "int", "smallint": "int",
    "long": "long", "bigint": "long",
    "double": "double", "float": "double", "real": "double", "double precision": "double",
    "decimal": "decimal", "numeric": "decimal", "bigdecimal": "decimal", "money": "decimal",
    "boolean": "boolean", "bool": "boolean",
    "date": "date", "fecha": "date",
    "datetime": "datetime", "timestamp": "datetime", "fechahora": "datetime",
    "uuid": "uuid",
}
TIPOS_CANONICOS = ["String", "int", "long", "double", "decimal", "boolean", "date", "datetime", "uuid"]

TIPOS_RELACION: dict[str, TipoRelacion] = {
    "association": TipoRelacion.ASOCIACION, "asociacion": TipoRelacion.ASOCIACION,
    "inheritance": TipoRelacion.HERENCIA, "generalization": TipoRelacion.HERENCIA, "herencia": TipoRelacion.HERENCIA,
    "aggregation": TipoRelacion.AGREGACION, "agregacion": TipoRelacion.AGREGACION,
    "composition": TipoRelacion.COMPOSICION, "composicion": TipoRelacion.COMPOSICION,
}
VISIBILIDADES: dict[str, VisibilidadMiembro] = {
    "public": VisibilidadMiembro.PUBLICO, "publico": VisibilidadMiembro.PUBLICO, "+": VisibilidadMiembro.PUBLICO,
    "private": VisibilidadMiembro.PRIVADO, "privado": VisibilidadMiembro.PRIVADO, "-": VisibilidadMiembro.PRIVADO,
    "protected": VisibilidadMiembro.PROTEGIDO, "protegido": VisibilidadMiembro.PROTEGIDO, "#": VisibilidadMiembro.PROTEGIDO,
    "package": VisibilidadMiembro.PAQUETE, "paquete": VisibilidadMiembro.PAQUETE, "~": VisibilidadMiembro.PAQUETE,
}
CARDINALIDADES = sorted(MULTIPLICIDADES_VALIDAS)

_ATRIBUTO_DATA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Nombre del atributo en camelCase, ej. fechaNacimiento"},
        "type": {"type": "string", "enum": TIPOS_CANONICOS, "description": "Tipo de dato"},
        "visibility": {"type": "string", "enum": ["private", "public", "protected", "package"]},
    },
    "required": ["name", "type"],
}

ESQUEMA_HERRAMIENTA = {
    "type": "function",
    "function": {
        "name": "apply_diagram_mutations",
        "description": (
            "Aplica un lote de cambios al diagrama de clases compartido del equipo, de forma atómica. "
            "Usá tempId en las acciones ADD_* para poder referenciar en el mismo lote lo que acabás de crear."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mensaje": {
                    "type": "string",
                    "description": "Respuesta para el chat, dirigida por su nombre a quien preguntó, explicando el cambio.",
                },
                "acciones": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ACCIONES},
                            "tempId": {"type": ["string", "null"], "description": "Id provisional (ADD_*)."},
                            "entityId": {"type": ["string", "null"], "description": "Id, tempId o nombre de la clase."},
                            "attributeId": {"type": ["string", "null"], "description": "Id o nombre del atributo."},
                            "relationshipId": {"type": ["string", "null"], "description": "Id o tempId de la relación."},
                            "entityData": {
                                "type": ["object", "null"],
                                "properties": {
                                    "name": {"type": "string", "description": "Nombre de la clase en PascalCase"},
                                    "isAbstract": {"type": "boolean"},
                                    "stereotype": {"type": ["string", "null"]},
                                    "attributes": {"type": "array", "items": _ATRIBUTO_DATA},
                                },
                            },
                            "attributeData": {**_ATRIBUTO_DATA, "type": ["object", "null"], "required": []},
                            "relationshipData": {
                                "type": ["object", "null"],
                                "properties": {
                                    "sourceId": {"type": "string", "description": "Id, tempId o nombre de la clase origen"},
                                    "sourceCardinality": {"type": ["string", "null"], "enum": [*CARDINALIDADES, None]},
                                    "targetId": {"type": "string", "description": "Id, tempId o nombre de la clase destino"},
                                    "targetCardinality": {"type": ["string", "null"], "enum": [*CARDINALIDADES, None]},
                                    "type": {
                                        "type": "string",
                                        "enum": ["association", "inheritance", "aggregation", "composition"],
                                    },
                                    "label": {"type": ["string", "null"]},
                                    "associationClassId": {
                                        "type": ["string", "null"],
                                        "description": "Clase de asociación (N:M con atributos propios).",
                                    },
                                },
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            "required": ["mensaje", "acciones"],
        },
    },
}


class MutacionInvalidaError(Exception):
    """El lote no se puede aplicar (nada se modificó)."""


@dataclass
class ResultadoMutacion:
    diagrama: DiagramaIO
    resumen: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ubicación libre en el lienzo
# ---------------------------------------------------------------------------

ANCHO_CLASE = 200
PASO_X, PASO_Y = 260, 60
MARGEN = 40


def _alto(clase: ClaseIO) -> float:
    return 70 + 22 * (len(clase.atributos) + len(clase.metodos))


def _se_superponen(x, y, ancho, alto, otra: ClaseIO) -> bool:
    return not (
        x + ancho + MARGEN <= otra.pos_x
        or otra.pos_x + ANCHO_CLASE + MARGEN <= x
        or y + alto + MARGEN <= otra.pos_y
        or otra.pos_y + _alto(otra) + MARGEN <= y
    )


def posicion_libre(clases: list[ClaseIO], alto: float, cerca_de: ClaseIO | None = None) -> tuple[float, float]:
    """Primera celda libre de una grilla; si hay una clase relacionada, se
    buscan primero las celdas más cercanas a ella."""
    candidatos = [(c * PASO_X, f * PASO_Y) for f in range(0, 60) for c in range(0, 6)]
    if cerca_de is not None:
        cx, cy = cerca_de.pos_x, cerca_de.pos_y
        candidatos.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    for x, y in candidatos:
        if not any(_se_superponen(x, y, ANCHO_CLASE, alto, otra) for otra in clases):
            return float(x), float(y)
    maximo = max((c.pos_y + _alto(c) for c in clases), default=0)
    return 0.0, float(maximo + MARGEN * 2)


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------


def _pascal(nombre: str) -> str:
    partes = nombre.replace("_", " ").split()
    if len(partes) <= 1:
        n = nombre.strip()
        return n[:1].upper() + n[1:]
    return "".join(p[:1].upper() + p[1:] for p in partes)


class _Aplicador:
    def __init__(self, diagrama: DiagramaIO) -> None:
        self.d = diagrama.model_copy(deep=True)
        self.temp: dict[str, str] = {}
        self.resumen: list[str] = []
        self.ultima_referida: ClaseIO | None = None

    # -- resolución ---------------------------------------------------------------
    def clase(self, ref: str | None, i: int) -> ClaseIO:
        if not ref:
            raise MutacionInvalidaError(f"Acción {i + 1}: falta la clase (entityId).")
        real = self.temp.get(ref, ref)
        for c in self.d.clases:
            if c.id == real:
                return c
        objetivo = normalizar_nombre(ref).replace(" ", "")
        for c in self.d.clases:
            if normalizar_nombre(c.nombre).replace(" ", "") == objetivo:
                return c
        raise MutacionInvalidaError(f'Acción {i + 1}: no existe la clase "{ref}".')

    def atributo(self, clase: ClaseIO, ref: str | None, i: int) -> AtributoIO:
        if not ref:
            raise MutacionInvalidaError(f"Acción {i + 1}: falta el atributo (attributeId).")
        for a in clase.atributos:
            if a.id == ref or normalizar_nombre(a.nombre) == normalizar_nombre(ref):
                return a
        raise MutacionInvalidaError(f'Acción {i + 1}: la clase {clase.nombre} no tiene el atributo "{ref}".')

    def relacion(self, ref: str | None, i: int) -> RelacionIO:
        real = self.temp.get(ref or "", ref)
        for r in self.d.relaciones:
            if r.id == real:
                return r
        raise MutacionInvalidaError(f'Acción {i + 1}: no existe la relación "{ref}".')

    # -- validaciones de valores ----------------------------------------------------
    @staticmethod
    def tipo_atributo(valor: str | None, i: int) -> str:
        if not valor:
            return "String"
        canonico = TIPOS_ATRIBUTO.get(valor.strip().lower())
        if canonico is None:
            raise MutacionInvalidaError(
                f'Acción {i + 1}: tipo "{valor}" no válido. Usá uno de: {", ".join(TIPOS_CANONICOS)}.'
            )
        return canonico

    @staticmethod
    def visibilidad(valor: str | None) -> VisibilidadMiembro:
        return VISIBILIDADES.get((valor or "private").strip().lower(), VisibilidadMiembro.PRIVADO)

    @staticmethod
    def cardinalidad(valor: str | None, i: int) -> str | None:
        if valor in (None, ""):
            return None
        if valor not in MULTIPLICIDADES_VALIDAS:
            raise MutacionInvalidaError(
                f'Acción {i + 1}: cardinalidad "{valor}" no válida. Usá una de: {", ".join(CARDINALIDADES)}.'
            )
        return valor

    def nuevo_atributo(self, clase: ClaseIO, datos: dict, i: int) -> AtributoIO:
        nombre = (datos.get("name") or "").strip()
        if not nombre:
            raise MutacionInvalidaError(f"Acción {i + 1}: un atributo no tiene nombre.")
        if any(normalizar_nombre(a.nombre) == normalizar_nombre(nombre) for a in clase.atributos):
            raise MutacionInvalidaError(f'Acción {i + 1}: {clase.nombre} ya tiene un atributo "{nombre}".')
        return AtributoIO(
            id=str(uuid.uuid4()),
            nombre=nombre,
            tipo=self.tipo_atributo(datos.get("type"), i),
            visibilidad=self.visibilidad(datos.get("visibility")),
            orden=len(clase.atributos),
        )

    # -- acciones -----------------------------------------------------------------
    def aplicar(self, i: int, a: dict) -> None:
        accion = (a.get("action") or "").upper()
        metodo = getattr(self, "_" + accion.lower(), None)
        if accion not in ACCIONES or metodo is None:
            raise MutacionInvalidaError(f'Acción {i + 1}: acción desconocida "{a.get("action")}".')
        metodo(i, a)

    def _add_entity(self, i, a):
        datos = a.get("entityData") or {}
        nombre = _pascal((datos.get("name") or "").strip())
        if not nombre:
            raise MutacionInvalidaError(f"Acción {i + 1}: la clase nueva no tiene nombre.")
        if any(normalizar_nombre(c.nombre) == normalizar_nombre(nombre) for c in self.d.clases):
            raise MutacionInvalidaError(f'Acción {i + 1}: ya existe una clase "{nombre}".')
        clase = ClaseIO(
            id=str(uuid.uuid4()),
            nombre=nombre,
            estereotipo=(datos.get("stereotype") or None),
            es_abstracta=bool(datos.get("isAbstract")),
            pos_x=0,
            pos_y=0,
            atributos=[],
            metodos=[],
        )
        for attr in datos.get("attributes") or []:
            clase.atributos.append(self.nuevo_atributo(clase, attr, i))
        clase.pos_x, clase.pos_y = posicion_libre(self.d.clases, _alto(clase))
        self.d.clases.append(clase)
        if a.get("tempId"):
            self.temp[a["tempId"]] = clase.id
        detalle = f" con {len(clase.atributos)} atributo(s)" if clase.atributos else ""
        self.resumen.append(f"Se crea la clase {clase.nombre}{detalle}.")

    def _update_entity(self, i, a):
        clase = self.clase(a.get("entityId"), i)
        datos = a.get("entityData") or {}
        cambios = []
        if datos.get("name") and datos["name"].strip() != clase.nombre:
            nuevo = _pascal(datos["name"].strip())
            if any(c.id != clase.id and normalizar_nombre(c.nombre) == normalizar_nombre(nuevo) for c in self.d.clases):
                raise MutacionInvalidaError(f'Acción {i + 1}: ya existe una clase "{nuevo}".')
            cambios.append(f"se renombra {clase.nombre} a {nuevo}")
            clase.nombre = nuevo
        if "isAbstract" in datos and datos["isAbstract"] is not None:
            clase.es_abstracta = bool(datos["isAbstract"])
            cambios.append(f"{clase.nombre} {'pasa a ser abstracta' if clase.es_abstracta else 'deja de ser abstracta'}")
        if "stereotype" in datos:
            clase.estereotipo = datos.get("stereotype") or None
        for attr in datos.get("attributes") or []:
            clase.atributos.append(self.nuevo_atributo(clase, attr, i))
            cambios.append(f"se agrega {attr.get('name')} a {clase.nombre}")
        self.resumen.append((("; ".join(cambios)) or f"Se actualiza {clase.nombre}").capitalize() + ".")

    def _delete_entity(self, i, a):
        clase = self.clase(a.get("entityId"), i)
        self.d.clases = [c for c in self.d.clases if c.id != clase.id]
        antes = len(self.d.relaciones)
        self.d.relaciones = [
            r for r in self.d.relaciones if clase.id not in (r.id_clase_origen, r.id_clase_destino)
        ]
        for r in self.d.relaciones:
            if r.id_clase_asociacion == clase.id:
                r.id_clase_asociacion = None
        quitadas = antes - len(self.d.relaciones)
        extra = f" (y {quitadas} relación(es) suya(s))" if quitadas else ""
        self.resumen.append(f"Se elimina la clase {clase.nombre}{extra}.")

    def _add_attribute(self, i, a):
        clase = self.clase(a.get("entityId"), i)
        datos = a.get("attributeData") or {}
        attr = self.nuevo_atributo(clase, datos, i)
        clase.atributos.append(attr)
        self.resumen.append(f"Se agrega el atributo {attr.nombre}: {attr.tipo} a {clase.nombre}.")

    def _update_attribute(self, i, a):
        clase = self.clase(a.get("entityId"), i)
        attr = self.atributo(clase, a.get("attributeId"), i)
        datos = a.get("attributeData") or {}
        if datos.get("name"):
            attr.nombre = datos["name"].strip()
        if datos.get("type"):
            attr.tipo = self.tipo_atributo(datos["type"], i)
        if datos.get("visibility"):
            attr.visibilidad = self.visibilidad(datos["visibility"])
        self.resumen.append(f"Se modifica el atributo {attr.nombre} de {clase.nombre}.")

    def _delete_attribute(self, i, a):
        clase = self.clase(a.get("entityId"), i)
        attr = self.atributo(clase, a.get("attributeId"), i)
        clase.atributos = [x for x in clase.atributos if x.id != attr.id]
        self.resumen.append(f"Se elimina el atributo {attr.nombre} de {clase.nombre}.")

    def _datos_relacion(self, i, datos: dict, base: RelacionIO | None = None) -> dict:
        res: dict = {}
        if datos.get("sourceId") or base is None:
            res["id_clase_origen"] = self.clase(datos.get("sourceId"), i).id
        if datos.get("targetId") or base is None:
            res["id_clase_destino"] = self.clase(datos.get("targetId"), i).id
        if datos.get("type") or base is None:
            tipo = TIPOS_RELACION.get(normalizar_nombre(datos.get("type") or "association"))
            if tipo is None:
                raise MutacionInvalidaError(f'Acción {i + 1}: tipo de relación "{datos.get("type")}" no válido.')
            res["tipo"] = tipo
        for clave, campo in (("sourceCardinality", "multiplicidad_origen"), ("targetCardinality", "multiplicidad_destino")):
            if clave in datos:
                res[campo] = self.cardinalidad(datos.get(clave), i)
        if "label" in datos:
            res["etiqueta"] = (datos.get("label") or None) and datos["label"][:100]
        if datos.get("associationClassId"):
            res["id_clase_asociacion"] = self.clase(datos["associationClassId"], i).id
        return res

    @staticmethod
    def _orientar_todo_parte(campos: dict) -> None:
        """Composición/agregación: el origen es el TODO. En UML la
        multiplicidad del lado del todo es como mucho 1, así que si el modelo
        las mandó al revés (todo con "*" y parte con "1") se invierte de forma
        determinística, sin depender de que el prompt se respete."""
        if campos.get("tipo") not in (TipoRelacion.COMPOSICION, TipoRelacion.AGREGACION):
            return
        plurales = {"*", "0..*", "1..*"}
        mo, md = campos.get("multiplicidad_origen"), campos.get("multiplicidad_destino")
        if mo in plurales and md in ("1", "0..1"):
            campos["id_clase_origen"], campos["id_clase_destino"] = campos["id_clase_destino"], campos["id_clase_origen"]
            campos["multiplicidad_origen"], campos["multiplicidad_destino"] = md, mo

    def _add_relationship(self, i, a):
        campos = self._datos_relacion(i, a.get("relationshipData") or {})
        self._orientar_todo_parte(campos)
        if campos["id_clase_origen"] == campos["id_clase_destino"] and campos["tipo"] == TipoRelacion.HERENCIA:
            raise MutacionInvalidaError(f"Acción {i + 1}: una clase no puede heredar de sí misma.")
        if campos["tipo"] == TipoRelacion.HERENCIA:
            campos["multiplicidad_origen"] = campos["multiplicidad_destino"] = None
        rel = RelacionIO(id=str(uuid.uuid4()), **campos)
        self.d.relaciones.append(rel)
        if a.get("tempId"):
            self.temp[a["tempId"]] = rel.id
        nombres = {c.id: c.nombre for c in self.d.clases}
        mult = ""
        if rel.multiplicidad_origen or rel.multiplicidad_destino:
            mult = f" ({rel.multiplicidad_origen or '?'} a {rel.multiplicidad_destino or '?'})"
        self.resumen.append(
            f"Se relaciona {nombres[rel.id_clase_origen]} con {nombres[rel.id_clase_destino]}: "
            f"{rel.tipo.value.lower()}{mult}."
        )

    def _update_relationship(self, i, a):
        rel = self.relacion(a.get("relationshipId"), i)
        for campo, valor in self._datos_relacion(i, a.get("relationshipData") or {}, base=rel).items():
            setattr(rel, campo, valor)
        if rel.tipo == TipoRelacion.HERENCIA:
            rel.multiplicidad_origen = rel.multiplicidad_destino = None
        self.resumen.append("Se modifica una relación.")

    def _delete_relationship(self, i, a):
        rel = self.relacion(a.get("relationshipId"), i)
        self.d.relaciones = [r for r in self.d.relaciones if r.id != rel.id]
        self.resumen.append("Se elimina una relación.")


def aplicar_mutaciones(diagrama: DiagramaIO, acciones: list[dict]) -> ResultadoMutacion:
    """Aplica el lote sobre una COPIA. Lanza `MutacionInvalidaError` sin
    modificar nada si alguna acción no es válida."""
    if not acciones:
        raise MutacionInvalidaError("El lote no tiene acciones.")
    ap = _Aplicador(diagrama)
    for i, accion in enumerate(acciones):
        if not isinstance(accion, dict):
            raise MutacionInvalidaError(f"Acción {i + 1}: formato inválido.")
        ap.aplicar(i, accion)
    try:
        validar_diagrama(ap.d)
    except HTTPException as err:
        raise MutacionInvalidaError(str(err.detail)) from err
    return ResultadoMutacion(diagrama=ap.d, resumen=ap.resumen)
