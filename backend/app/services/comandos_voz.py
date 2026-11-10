"""CU11 — interpretación de comandos de voz.

Este módulo SOLO interpreta: recibe el texto ya transcrito por el navegador
(Web Speech API), usa la API de OpenAI (function calling / tools) para
determinar cuál de las 5 acciones soportadas corresponde, resuelve los
nombres de clase que citó el modelo contra las clases reales del proyecto
(mismo criterio `casefold()` que ya usa `validar_diagrama`), y devuelve una
`AccionVoz` con los ids ya resueltos. Nunca persiste nada en la base de datos
-- quien aplica la acción es el frontend, llamando a las funciones que ya
existen en `useDiagrama.ts` (`agregarClase`/`actualizarClase`/`eliminarClase`/
`crearRelacion`), que ya disparan el autoguardado HTTP y la sincronización a
Yjs (CU10). Así se evita duplicar validación/persistencia/ids nuevos.

`_llamar_openai` es el único punto que toca la red -- es la función que se
monkeypatchea en los tests (`backend/tests/test_comandos_voz.py`) para no
pegarle nunca a la API real, mismo patrón que ya usa
`test_ws_diagramas.py` (`monkeypatch.setattr(yjs_rooms, "DEBOUNCE_SEGUNDOS", ...)`).

`construir_tools()` y `resolver_accion()` son públicas a propósito: CU13
(`app/services/agente.py`) las reutiliza tal cual para no duplicar las 5
tools de function calling ni la resolución nombre→id -- ve su propia llamada
a OpenAI (multi-turno, con historial) pero comparte este mismo "motor" de
acciones.

**Lenguaje natural (CU11, segunda versión)**: la voz ya no usa esas 5 tools
sino `construir_tools_voz()`: una tool compuesta `modificar_diagrama` (crear
varias clases, agregar atributos a existentes y relacionarlas, todo en un
solo comando) + `eliminar_clase`/`renombrar_clase`. El modelo deduce el tipo
de relación y las multiplicidades por el dominio (el prompt trae la guía UML)
y relaciona una clase nueva con las existentes aunque la usuaria no lo diga,
si el vínculo es evidente. `_manejar_modificar_diagrama` es tolerante, igual
que el importador XMI: descarta o ajusta lo que no cierra (con advertencias)
en vez de hacer fallar todo el comando. CU13 no cambió: sigue con las 5 tools.
"""

from __future__ import annotations

import json

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.atributo import VisibilidadMiembro
from app.models.relacion import TipoRelacion
from app.schemas.comando_voz import (
    AccionAgregarAtributo,
    AccionCrearClase,
    AccionCrearRelacion,
    AccionEliminarClase,
    AccionModificarDiagrama,
    AccionRenombrarClase,
    AccionVoz,
    AtributoNuevoIO,
    AtributosAgregadosIO,
    ClaseNuevaIO,
    ExtremoRelacionIO,
    RelacionNuevaIO,
)
from app.schemas.diagrama import ClaseIO, DiagramaIO
from app.services.diagrama import MULTIPLICIDADES_VALIDAS, cargar_diagrama
from app.services.nombres import normalizar_nombre

MENSAJE_NO_SOPORTADO = (
    "No se entendió el comando o la acción no está soportada. Comandos soportados: "
    "crear clase, agregar atributo, eliminar clase, crear relación, renombrar clase."
)


class ComandoVozInvalidoError(Exception):
    """El texto no se pudo mapear a ninguna de las 5 acciones soportadas, los
    argumentos que devolvió el modelo no pasan la validación, o el comando
    referencia/duplica un nombre de clase que no corresponde. El router lo
    traduce a 422 -- nunca se toca el diagrama en este caso."""


class ComandoVozNoDisponibleError(Exception):
    """Timeout, error de red o rate-limit al llamar a OpenAI. El router lo
    traduce a 503 con un mensaje genérico -- nunca se expone el detalle
    crudo del proveedor externo."""


def construir_tools() -> list[dict]:
    visibilidades = [v.value for v in VisibilidadMiembro]
    tipos_relacion = [t.value for t in TipoRelacion]
    multiplicidades = sorted(MULTIPLICIDADES_VALIDAS)

    propiedades_atributo = {
        "nombre": {"type": "string", "description": "Nombre del atributo."},
        "tipo": {
            "type": ["string", "null"],
            "description": "Tipo de dato del atributo, ej. String, int, boolean. null si no se especificó.",
        },
        "visibilidad": {"type": "string", "enum": visibilidades},
    }

    return [
        {
            "type": "function",
            "function": {
                "name": "crear_clase",
                "description": (
                    "Crea una clase nueva en el diagrama UML, opcionalmente con "
                    "atributos ya especificados en el mismo comando."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nombre_clase": {"type": "string", "description": "Nombre de la clase a crear."},
                        "atributos": {
                            "type": "array",
                            "description": "Atributos mencionados en el mismo comando, si los hay.",
                            "items": {
                                "type": "object",
                                "properties": propiedades_atributo,
                                "required": ["nombre", "tipo", "visibilidad"],
                            },
                        },
                    },
                    "required": ["nombre_clase", "atributos"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "agregar_atributo",
                "description": "Agrega un atributo nuevo a una clase que YA EXISTE en el diagrama.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nombre_clase": {
                            "type": "string",
                            "description": "Nombre de la clase existente a la que se agrega el atributo.",
                        },
                        **propiedades_atributo,
                    },
                    "required": ["nombre_clase", "nombre", "tipo", "visibilidad"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "eliminar_clase",
                "description": "Elimina una clase existente del diagrama (y sus relaciones).",
                "parameters": {
                    "type": "object",
                    "properties": {"nombre_clase": {"type": "string"}},
                    "required": ["nombre_clase"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "crear_relacion",
                "description": "Crea una relación UML entre dos clases existentes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nombre_clase_origen": {"type": "string"},
                        "nombre_clase_destino": {"type": "string"},
                        "tipo_relacion": {"type": "string", "enum": tipos_relacion},
                        "multiplicidad_origen": {"type": ["string", "null"], "enum": [*multiplicidades, None]},
                        "multiplicidad_destino": {"type": ["string", "null"], "enum": [*multiplicidades, None]},
                    },
                    "required": [
                        "nombre_clase_origen",
                        "nombre_clase_destino",
                        "tipo_relacion",
                        "multiplicidad_origen",
                        "multiplicidad_destino",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "renombrar_clase",
                "description": "Cambia el nombre de una clase existente.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nombre_actual": {"type": "string"},
                        "nombre_nuevo": {"type": "string"},
                    },
                    "required": ["nombre_actual", "nombre_nuevo"],
                },
            },
        },
    ]


def resumen_diagrama(diagrama: DiagramaIO) -> str:
    """Estado del diagrama en texto para el prompt: clases con sus atributos y
    relaciones existentes. Lo comparten CU11 (acá) y CU13 (`agente.py`)."""
    if not diagrama.clases:
        return "(el diagrama está vacío todavía, no tiene ninguna clase)"

    nombres_por_id = {c.id: c.nombre for c in diagrama.clases}
    lineas = []
    for c in diagrama.clases:
        atributos = ", ".join(f"{a.nombre}: {a.tipo or 'sin tipo'}" for a in c.atributos) or "sin atributos"
        lineas.append(f'- Clase "{c.nombre}" ({atributos})')

    if diagrama.relaciones:
        lineas.append("Relaciones:")
        for r in diagrama.relaciones:
            origen = nombres_por_id.get(r.id_clase_origen, "?")
            destino = nombres_por_id.get(r.id_clase_destino, "?")
            mult = f" ({r.multiplicidad_origen or '?'} - {r.multiplicidad_destino or '?'})"
            lineas.append(f'- "{origen}" --{r.tipo.value.lower()}--> "{destino}"{mult}')

    return "\n".join(lineas)


def construir_tools_voz() -> list[dict]:
    """Tools de CU11: la compuesta `modificar_diagrama` + eliminar/renombrar
    (reutilizadas de `construir_tools()`, que sigue siendo la de CU13)."""
    visibilidades = [v.value for v in VisibilidadMiembro]
    tipos_relacion = [t.value for t in TipoRelacion]
    multiplicidades = [*sorted(MULTIPLICIDADES_VALIDAS), None]

    esquema_atributos = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre del atributo, en camelCase."},
                "tipo": {
                    "type": "string",
                    "description": "Tipo de dato (String, int, double, boolean, Date...). Deducilo del nombre si no se dijo.",
                },
                "visibilidad": {"type": "string", "enum": visibilidades},
            },
            "required": ["nombre", "tipo", "visibilidad"],
        },
    }

    modificar_diagrama = {
        "type": "function",
        "function": {
            "name": "modificar_diagrama",
            "description": (
                "Crea una o varias clases nuevas, agrega atributos a clases existentes y crea "
                "relaciones (entre clases nuevas y/o existentes), todo en un solo comando."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "clases_nuevas": {
                        "type": "array",
                        "description": "Clases que NO existen todavía en el diagrama.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nombre": {"type": "string", "description": "Singular, PascalCase."},
                                "atributos": esquema_atributos,
                            },
                            "required": ["nombre", "atributos"],
                        },
                    },
                    "atributos_para_clases_existentes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nombre_clase": {"type": "string"},
                                "atributos": esquema_atributos,
                            },
                            "required": ["nombre_clase", "atributos"],
                        },
                    },
                    "relaciones": {
                        "type": "array",
                        # Mismo orden que CU12 (reconocimiento_foto.py): cada
                        # multiplicidad inmediatamente después del nombre de su
                        # clase -- con las dos al final el modelo las cruzaba.
                        "items": {
                            "type": "object",
                            "properties": {
                                "razonamiento": {
                                    "type": "string",
                                    "description": "Una frase: por qué existe el vínculo y por qué es de ese tipo.",
                                },
                                "tipo": {"type": "string", "enum": tipos_relacion},
                                "clase_origen": {"type": "string"},
                                "multiplicidad_junto_a_clase_origen": {"type": ["string", "null"], "enum": multiplicidades},
                                "clase_destino": {"type": "string"},
                                "multiplicidad_junto_a_clase_destino": {"type": ["string", "null"], "enum": multiplicidades},
                                "etiqueta": {
                                    "type": ["string", "null"],
                                    "description": "Verbo corto que nombra el vínculo (realiza, contiene), o null.",
                                },
                            },
                            "required": [
                                "razonamiento",
                                "tipo",
                                "clase_origen",
                                "multiplicidad_junto_a_clase_origen",
                                "clase_destino",
                                "multiplicidad_junto_a_clase_destino",
                                "etiqueta",
                            ],
                        },
                    },
                },
                "required": ["clases_nuevas", "atributos_para_clases_existentes", "relaciones"],
            },
        },
    }

    otras = [t for t in construir_tools() if t["function"]["name"] in {"eliminar_clase", "renombrar_clase"}]
    return [modificar_diagrama, *otras]


def _prompt_sistema(diagrama: DiagramaIO) -> str:
    multiplicidades = ", ".join(sorted(MULTIPLICIDADES_VALIDAS))
    return (
        "Sos el intérprete de comandos de voz de un diagramador de clases UML. La usuaria "
        "habla en español (Bolivia/Latinoamérica), de forma natural y coloquial, y su voz ya "
        "fue transcrita a texto (puede traer errores de transcripción: \"clace\" = clase, "
        "palabras cortadas, muletillas como \"eh\", \"este\"). Entendé la INTENCIÓN, no las "
        "palabras exactas.\n\n"
        f"Estado ACTUAL del diagrama:\n{resumen_diagrama(diagrama)}\n\n"
        "Qué función usar:\n"
        "- Para crear clases, agregar atributos y/o relacionar clases usá SIEMPRE "
        "`modificar_diagrama`, aunque sea una sola cosa. Un comando puede pedir varias "
        "clases a la vez: incluí todas.\n"
        "- Para borrar una clase, `eliminar_clase`; para cambiarle el nombre, `renombrar_clase`.\n"
        "- Si el texto no tiene que ver con editar el diagrama o no se entiende en absoluto, "
        "llamá a `modificar_diagrama` con las tres listas vacías. No hay preguntas de vuelta: "
        "interpretá con la mejor información disponible.\n\n"
        "Clases y atributos:\n"
        "- Nombres de clase en singular y PascalCase (\"detalle de pedido\" -> DetallePedido, "
        "\"clientes\" -> Cliente). Atributos en camelCase (\"fecha de nacimiento\" -> "
        "fechaNacimiento).\n"
        "- Si una clase mencionada ya existe en el diagrama, NO la pongas en clases_nuevas: "
        "sus atributos nuevos van en atributos_para_clases_existentes, y en las relaciones "
        "usá su nombre exacto.\n"
        "- Si no se dice el tipo de un atributo, deducilo: nombre/correo/dirección/teléfono/"
        "descripción -> String; edad/cantidad/stock/número -> int; precio/total/monto/"
        "salario/peso -> double; fecha/fechaX -> Date; activo/disponible/esX -> boolean.\n"
        "- Visibilidad PRIVADO salvo que se diga otra. No agregues un atributo \"id\" salvo "
        "que se pida.\n\n"
        "Relaciones -- deducí el tipo por el significado, aunque la usuaria no lo nombre:\n"
        "- HERENCIA: \"X es un/una Y\", \"X es un tipo de Y\", \"X hereda de Y\". "
        "clase_origen = subclase (X), clase_destino = superclase (Y). Sin multiplicidades.\n"
        "- COMPOSICION: la parte no tiene sentido sin el todo y muere con él (Pedido-"
        "DetallePedido, Factura-LineaFactura, Casa-Habitacion, Libro-Capitulo). "
        "clase_origen = el todo, clase_destino = la parte.\n"
        "- AGREGACION: el todo agrupa partes que existen por su cuenta (Equipo-Jugador, "
        "Biblioteca-Libro, Departamento-Empleado, Curso-Estudiante). clase_origen = el todo, "
        "clase_destino = la parte.\n"
        "- ASOCIACION: cualquier otro vínculo (Cliente realiza Pedido, Medico atiende "
        "Paciente, Socio presta Libro). clase_origen = quien realiza la acción.\n"
        "- Ante la duda entre composición/agregación y asociación, elegí ASOCIACION.\n\n"
        f"Multiplicidades (solo {multiplicidades}): deducilas del lenguaje y del dominio. La "
        "multiplicidad junto a una clase X responde: ¿con cuántas X se vincula UNA instancia de "
        "la otra clase? Leé la relación en los dos sentidos: \"un Socio hace muchos Prestamos\" "
        "-> junto a Prestamo \"0..*\"; \"un Prestamo es de un solo Socio\" -> junto a Socio "
        "\"1\". \"al menos uno\" / \"varios\" -> \"1..*\"; \"puede tener uno\" -> \"0..1\"; una "
        "cantidad fija mayor a uno (\"cuatro ruedas\") -> \"1..*\". Siempre completá las dos "
        "multiplicidades, salvo en HERENCIA, donde van null.\n\n"
        "Relacionar sin que te lo pidan (IMPORTANTE): la usuaria espera que cada clase nueva "
        "quede conectada con el resto del modelo. Antes de responder, para CADA clase nueva "
        "revisá UNA POR UNA las clases del diagrama y las demás clases nuevas, y preguntate: "
        "¿en un sistema real estas dos clases estarían vinculadas directamente? Si la respuesta "
        "es claramente sí, agregá la relación aunque la usuaria no la haya mencionado (una "
        "Categoria nueva en un diagrama con Producto -> Categoria 1 -- 0..* Producto; un "
        "Pedido nuevo con Cliente -> Cliente 1 -- 0..* Pedido; un Paciente nuevo con Medico "
        "-> Medico 0..* -- 0..* Paciente). Solo vínculos directos y evidentes: no inventes "
        "relaciones dudosas, no relaciones entre sí clases que ya existían si no se pidió, y "
        "no repitas relaciones que ya están en el diagrama.\n\n"
        "Ejemplos:\n"
        "- \"quiero un cliente con nombre y correo que hace muchos pedidos con fecha y "
        "total\" -> clases_nuevas Cliente(nombre String, correo String) y Pedido(fecha Date, "
        "total double); relación ASOCIACION Cliente \"1\" -> Pedido \"0..*\", etiqueta "
        "\"realiza\".\n"
        "- (con Pedido ya existente) \"agregá detalle de pedido con cantidad y precio\" -> "
        "clases_nuevas DetallePedido(cantidad int, precio double); relación COMPOSICION "
        "Pedido \"1\" -> DetallePedido \"1..*\".\n"
        "- (con Cliente ya existente) \"un cliente VIP es un cliente con descuento\" -> "
        "clases_nuevas ClienteVip(descuento double); relación HERENCIA ClienteVip -> Cliente.\n"
        "- \"crear un equipo que tiene varios jugadores con nombre y dorsal\" -> Equipo, "
        "Jugador(nombre String, dorsal int); relación AGREGACION Equipo \"1\" -> Jugador \"1..*\".\n"
        "- (con Producto ya existente) \"al producto ponele precio y stock\" -> "
        "atributos_para_clases_existentes Producto(precio double, stock int)."
    )


def _llamar_openai(texto: str, prompt_sistema: str) -> tuple[str | None, dict | None]:
    if not settings.OPENAI_API_KEY:
        raise ComandoVozNoDisponibleError("OPENAI_API_KEY no está configurada en el servidor.")

    cliente = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        respuesta = cliente.chat.completions.create(
            model=settings.OPENAI_VOZ_MODEL,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": texto},
            ],
            tools=construir_tools_voz(),
            # "required": un comando de voz siempre es una edición. Con "auto"
            # gpt-4o a veces contestaba texto a un pedido válido; si de verdad
            # no se entiende, devuelve un modificar_diagrama vacío -> 422.
            tool_choice="required",
            parallel_tool_calls=False,
        )
    except (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError) as err:
        raise ComandoVozNoDisponibleError(str(err)) from err

    tool_calls = respuesta.choices[0].message.tool_calls
    if not tool_calls:
        return None, None

    llamada = tool_calls[0]
    try:
        argumentos = json.loads(llamada.function.arguments)
    except json.JSONDecodeError as err:
        raise ComandoVozInvalidoError(
            "El comando no se pudo interpretar completamente. Intenta de nuevo siendo más específico."
        ) from err
    return llamada.function.name, argumentos


def _resolver_clase(nombre: str, clases: list[ClaseIO]) -> ClaseIO:
    objetivo = normalizar_nombre(nombre)
    for clase in clases:
        if normalizar_nombre(clase.nombre) == objetivo:
            return clase
    raise ComandoVozInvalidoError(f'No se encontró ninguna clase llamada "{nombre}" en este proyecto.')


def _validar_nombre_disponible(nombre: str, clases: list[ClaseIO]) -> None:
    objetivo = nombre.strip().casefold()
    if any(c.nombre.strip().casefold() == objetivo for c in clases):
        raise ComandoVozInvalidoError(f'Ya existe una clase llamada "{nombre}" en este proyecto.')


def _atributo_desde_argumentos(argumentos: dict) -> AtributoNuevoIO:
    try:
        return AtributoNuevoIO(**argumentos)
    except ValidationError as err:
        raise ComandoVozInvalidoError(
            "El comando no se pudo interpretar completamente. Intenta de nuevo siendo más específico."
        ) from err


def _manejar_crear_clase(argumentos: dict, clases: list[ClaseIO]) -> AccionCrearClase:
    nombre_clase = argumentos.get("nombre_clase")
    if not nombre_clase or not isinstance(nombre_clase, str):
        raise ComandoVozInvalidoError(MENSAJE_NO_SOPORTADO)
    _validar_nombre_disponible(nombre_clase, clases)

    atributos_crudos = argumentos.get("atributos") or []
    try:
        atributos = [AtributoNuevoIO(**a) for a in atributos_crudos]
    except ValidationError as err:
        raise ComandoVozInvalidoError(
            "El comando no se pudo interpretar completamente. Intenta de nuevo siendo más específico."
        ) from err

    resumen = f"Se creó la clase \"{nombre_clase}\""
    resumen += f" con {len(atributos)} atributo{'s' if len(atributos) != 1 else ''}." if atributos else "."
    return AccionCrearClase(nombre_clase=nombre_clase, atributos=atributos, resumen=resumen)


def _manejar_agregar_atributo(argumentos: dict, clases: list[ClaseIO]) -> AccionAgregarAtributo:
    nombre_clase = argumentos.get("nombre_clase")
    if not nombre_clase or not isinstance(nombre_clase, str):
        raise ComandoVozInvalidoError(MENSAJE_NO_SOPORTADO)
    clase = _resolver_clase(nombre_clase, clases)
    atributo = _atributo_desde_argumentos(
        {
            "nombre": argumentos.get("nombre"),
            "tipo": argumentos.get("tipo"),
            "visibilidad": argumentos.get("visibilidad", VisibilidadMiembro.PRIVADO.value),
        }
    )
    resumen = f'Se agregó el atributo "{atributo.nombre}" a la clase "{clase.nombre}".'
    return AccionAgregarAtributo(id_clase=clase.id, nombre_clase=clase.nombre, atributo=atributo, resumen=resumen)


def _manejar_eliminar_clase(argumentos: dict, clases: list[ClaseIO]) -> AccionEliminarClase:
    nombre_clase = argumentos.get("nombre_clase")
    if not nombre_clase or not isinstance(nombre_clase, str):
        raise ComandoVozInvalidoError(MENSAJE_NO_SOPORTADO)
    clase = _resolver_clase(nombre_clase, clases)
    resumen = f'Se eliminó la clase "{clase.nombre}".'
    return AccionEliminarClase(id_clase=clase.id, nombre_clase=clase.nombre, resumen=resumen)


def _manejar_crear_relacion(argumentos: dict, clases: list[ClaseIO]) -> AccionCrearRelacion:
    nombre_origen = argumentos.get("nombre_clase_origen")
    nombre_destino = argumentos.get("nombre_clase_destino")
    tipo_relacion = argumentos.get("tipo_relacion")
    if not nombre_origen or not nombre_destino or tipo_relacion not in {t.value for t in TipoRelacion}:
        raise ComandoVozInvalidoError(MENSAJE_NO_SOPORTADO)

    origen = _resolver_clase(nombre_origen, clases)
    destino = _resolver_clase(nombre_destino, clases)

    for multiplicidad in (argumentos.get("multiplicidad_origen"), argumentos.get("multiplicidad_destino")):
        if multiplicidad is not None and multiplicidad not in MULTIPLICIDADES_VALIDAS:
            raise ComandoVozInvalidoError(MENSAJE_NO_SOPORTADO)

    resumen = f'Se creó una relación de {tipo_relacion.lower()} entre "{origen.nombre}" y "{destino.nombre}".'
    return AccionCrearRelacion(
        id_clase_origen=origen.id,
        id_clase_destino=destino.id,
        nombre_clase_origen=origen.nombre,
        nombre_clase_destino=destino.nombre,
        tipo=TipoRelacion(tipo_relacion),
        multiplicidad_origen=argumentos.get("multiplicidad_origen"),
        multiplicidad_destino=argumentos.get("multiplicidad_destino"),
        resumen=resumen,
    )


def _manejar_renombrar_clase(argumentos: dict, clases: list[ClaseIO]) -> AccionRenombrarClase:
    nombre_actual = argumentos.get("nombre_actual")
    nombre_nuevo = argumentos.get("nombre_nuevo")
    if not nombre_actual or not nombre_nuevo:
        raise ComandoVozInvalidoError(MENSAJE_NO_SOPORTADO)

    clase = _resolver_clase(nombre_actual, clases)
    otras = [c for c in clases if c.id != clase.id]
    _validar_nombre_disponible(nombre_nuevo, otras)

    resumen = f'Se cambió el nombre de "{clase.nombre}" a "{nombre_nuevo}".'
    return AccionRenombrarClase(id_clase=clase.id, nombre_anterior=clase.nombre, nombre_nuevo=nombre_nuevo, resumen=resumen)


def _pascal_case(nombre: str) -> str:
    """ "detalle pedido" -> "DetallePedido". Solo toca la primera letra de cada
    palabra (así "ClienteVIP" queda igual)."""
    return "".join(p[:1].upper() + p[1:] for p in nombre.split())


def _atributos_validos(crudos: list, existentes: set[str], nombre_clase: str, advertencias: list[str]) -> list[AtributoNuevoIO]:
    """Atributos del modelo ya validados, sin repetir los que la clase ya tiene
    (`existentes`, normalizados; se va completando con los nuevos)."""
    atributos = []
    for crudo in crudos or []:
        if not isinstance(crudo, dict) or crudo.get("visibilidad") not in {v.value for v in VisibilidadMiembro}:
            crudo = {**(crudo if isinstance(crudo, dict) else {}), "visibilidad": VisibilidadMiembro.PRIVADO.value}
        try:
            atributo = AtributoNuevoIO(nombre=crudo.get("nombre"), tipo=crudo.get("tipo") or None, visibilidad=crudo["visibilidad"])
        except ValidationError:
            advertencias.append(f'Se omitió un atributo sin nombre válido en "{nombre_clase}".')
            continue
        clave = normalizar_nombre(atributo.nombre)
        if clave in existentes:
            advertencias.append(f'"{nombre_clase}" ya tenía el atributo "{atributo.nombre}", no se repitió.')
            continue
        existentes.add(clave)
        atributos.append(atributo)
    return atributos


def _clave_clase(nombre: str) -> str:
    """Clave de comparación de CU11: `normalizar_nombre` y además sin espacios,
    porque la voz dice "detalle pedido" y la clase se llama DetallePedido."""
    return normalizar_nombre(nombre).replace(" ", "")


def _manejar_modificar_diagrama(argumentos: dict, diagrama: DiagramaIO) -> AccionModificarDiagrama:
    """Arma la acción compuesta a partir de lo que devolvió el modelo, contra
    el diagrama actual. Tolerante: lo que no cierra se descarta o se ajusta con
    una advertencia; solo falla si no queda nada para hacer."""
    advertencias: list[str] = []
    existentes = {_clave_clase(c.nombre): c for c in diagrama.clases}

    # Clases nuevas (y las "nuevas" que en realidad ya existen -> sus
    # atributos se agregan a la existente, en vez de rechazar el comando).
    nuevas: dict[str, ClaseNuevaIO] = {}
    atributos_nuevas: dict[str, set[str]] = {}
    agregados: dict[str, AtributosAgregadosIO] = {}
    atributos_existentes: dict[str, set[str]] = {
        c.id: {normalizar_nombre(a.nombre) for a in c.atributos} for c in diagrama.clases
    }

    def agregar_a_existente(clase: ClaseIO, crudos: list) -> None:
        atributos = _atributos_validos(crudos, atributos_existentes[clase.id], clase.nombre, advertencias)
        if not atributos:
            return
        if clase.id in agregados:
            agregados[clase.id].atributos.extend(atributos)
        else:
            agregados[clase.id] = AtributosAgregadosIO(id_clase=clase.id, nombre_clase=clase.nombre, atributos=atributos)

    for crudo in argumentos.get("clases_nuevas") or []:
        nombre = _pascal_case(str((crudo or {}).get("nombre") or ""))
        if not nombre:
            advertencias.append("Se omitió una clase sin nombre.")
            continue
        clave = _clave_clase(nombre)
        if clave in existentes:
            agregar_a_existente(existentes[clave], crudo.get("atributos"))
            continue
        if clave not in nuevas:
            nuevas[clave] = ClaseNuevaIO(nombre=nombre, atributos=[])
            atributos_nuevas[clave] = set()
        nuevas[clave].atributos.extend(
            _atributos_validos(crudo.get("atributos"), atributos_nuevas[clave], nombre, advertencias)
        )

    for crudo in argumentos.get("atributos_para_clases_existentes") or []:
        nombre = str((crudo or {}).get("nombre_clase") or "")
        clave = _clave_clase(nombre)
        if clave in existentes:
            agregar_a_existente(existentes[clave], crudo.get("atributos"))
        elif clave in nuevas:
            nuevas[clave].atributos.extend(
                _atributos_validos(crudo.get("atributos"), atributos_nuevas[clave], nuevas[clave].nombre, advertencias)
            )
        else:
            advertencias.append(f'No existe la clase "{nombre}": no se le agregaron atributos.')

    # Relaciones: cada extremo es una clase existente (con id) o una nueva
    # del mismo comando (sin id, la resuelve el frontend por nombre).
    def extremo(nombre: str) -> ExtremoRelacionIO | None:
        clave = _clave_clase(nombre)
        if clave in existentes:
            return ExtremoRelacionIO(id_clase=existentes[clave].id, nombre_clase=existentes[clave].nombre)
        if clave in nuevas:
            return ExtremoRelacionIO(id_clase=None, nombre_clase=nuevas[clave].nombre)
        return None

    nombres_por_id = {c.id: _clave_clase(c.nombre) for c in diagrama.clases}
    vistas = {
        (frozenset({nombres_por_id.get(r.id_clase_origen), nombres_por_id.get(r.id_clase_destino)}), r.tipo)
        for r in diagrama.relaciones
    }
    relaciones: list[RelacionNuevaIO] = []
    for crudo in argumentos.get("relaciones") or []:
        crudo = crudo or {}
        tipo = crudo.get("tipo")
        nombre_origen = str(crudo.get("clase_origen") or "")
        nombre_destino = str(crudo.get("clase_destino") or "")
        if tipo not in {t.value for t in TipoRelacion}:
            advertencias.append(f'Se descartó una relación entre "{nombre_origen}" y "{nombre_destino}" de tipo desconocido.')
            continue
        origen, destino = extremo(nombre_origen), extremo(nombre_destino)
        if origen is None or destino is None:
            faltante = nombre_origen if origen is None else nombre_destino
            advertencias.append(f'Se descartó la relación con "{faltante}": esa clase no existe.')
            continue
        clave_par = _clave_clase(origen.nombre_clase), _clave_clase(destino.nombre_clase)
        if clave_par[0] == clave_par[1]:
            advertencias.append(f'Se descartó una relación de "{origen.nombre_clase}" consigo misma.')
            continue
        firma = (frozenset(clave_par), TipoRelacion(tipo))
        if firma in vistas:
            continue
        vistas.add(firma)

        es_herencia = tipo == TipoRelacion.HERENCIA.value
        mult_origen = crudo.get("multiplicidad_junto_a_clase_origen")
        mult_destino = crudo.get("multiplicidad_junto_a_clase_destino")
        etiqueta = (crudo.get("etiqueta") or "").strip() or None
        relaciones.append(
            RelacionNuevaIO(
                origen=origen,
                destino=destino,
                tipo=TipoRelacion(tipo),
                multiplicidad_origen=None if es_herencia or mult_origen not in MULTIPLICIDADES_VALIDAS else mult_origen,
                multiplicidad_destino=None if es_herencia or mult_destino not in MULTIPLICIDADES_VALIDAS else mult_destino,
                etiqueta=None if es_herencia else etiqueta,
            )
        )

    if not nuevas and not agregados and not relaciones:
        raise ComandoVozInvalidoError(
            " ".join(advertencias)
            if advertencias
            else "No se entendió qué cambio hacer en el diagrama. Probá, por ejemplo: "
            "\"crear un cliente con nombre que hace muchos pedidos\"."
        )

    accion = AccionModificarDiagrama(
        clases_nuevas=list(nuevas.values()),
        atributos_agregados=list(agregados.values()),
        relaciones=relaciones,
        advertencias=advertencias,
        resumen="",
    )
    accion.resumen = _resumen_modificacion(accion)
    return accion


_NOMBRE_TIPO_RELACION = {
    TipoRelacion.ASOCIACION: "asociación",
    TipoRelacion.HERENCIA: "herencia",
    TipoRelacion.AGREGACION: "agregación",
    TipoRelacion.COMPOSICION: "composición",
}


def _plural(cantidad: int, singular: str, plural: str) -> str:
    return f"{cantidad} {singular if cantidad == 1 else plural}"


def _resumen_modificacion(accion: AccionModificarDiagrama) -> str:
    partes = []
    if accion.clases_nuevas:
        nombres = ", ".join(c.nombre for c in accion.clases_nuevas)
        partes.append(f"{'Se creó la clase' if len(accion.clases_nuevas) == 1 else 'Se crearon las clases'} {nombres}")
    for grupo in accion.atributos_agregados:
        partes.append(f"se {'agregó' if len(grupo.atributos) == 1 else 'agregaron'} {_plural(len(grupo.atributos), 'atributo', 'atributos')} a {grupo.nombre_clase}")
    if accion.relaciones:
        detalle = ", ".join(
            f"{r.origen.nombre_clase} y {r.destino.nombre_clase} ({_NOMBRE_TIPO_RELACION[r.tipo]})" for r in accion.relaciones
        )
        partes.append(f"se {'relacionó' if len(accion.relaciones) == 1 else 'relacionaron'} {detalle}")
    texto = "; ".join(partes)
    return texto[:1].upper() + texto[1:] + "."


_MANEJADORES = {
    "crear_clase": _manejar_crear_clase,
    "agregar_atributo": _manejar_agregar_atributo,
    "eliminar_clase": _manejar_eliminar_clase,
    "crear_relacion": _manejar_crear_relacion,
    "renombrar_clase": _manejar_renombrar_clase,
}


def resolver_accion(nombre_tool: str | None, argumentos: dict | None, clases: list[ClaseIO]) -> AccionVoz:
    """Dado el nombre/argumentos de una tool ya devuelta por OpenAI (propios o
    de CU13), despacha al manejador de la acción correspondiente y arma la
    `AccionVoz` con ids ya resueltos. Levanta `ComandoVozInvalidoError` si
    `nombre_tool` es `None` (no hubo tool_call) o no corresponde a ninguna de
    las 5 acciones soportadas."""
    manejador = _MANEJADORES.get(nombre_tool) if nombre_tool else None
    if manejador is None:
        raise ComandoVozInvalidoError(MENSAJE_NO_SOPORTADO)

    return manejador(argumentos, clases)


def interpretar_comando(proyecto_id: int, texto: str, db: Session) -> AccionVoz:
    diagrama = cargar_diagrama(proyecto_id, db)
    prompt = _prompt_sistema(diagrama)
    nombre_tool, argumentos = _llamar_openai(texto, prompt)
    if nombre_tool == "modificar_diagrama":
        return _manejar_modificar_diagrama(argumentos or {}, diagrama)
    return resolver_accion(nombre_tool, argumentos, diagrama.clases)
