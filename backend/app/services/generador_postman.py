"""
Colección Postman (v2.1) del backend generado — RF-BASE-08/09.

Pensada para ejecutarse completa con "Run collection" sin tocar nada:
1. **CRUD**: por cada clase (en orden de dependencias: primero las referidas
   por FK obligatoria) crea, lista, obtiene y actualiza. Cada "Crear" guarda
   el id devuelto en una variable de colección (`{{personaId}}`) que usan
   las peticiones siguientes.
2. **Relaciones N:M**: vincula (201), lista en ambos sentidos (200),
   desvincula (204) y vuelve a vincular.
3. **Integridad referencial**: una referencia a un id inexistente → 400.
4. **Eliminar**: borra en orden inverso (204).

Cada petición trae un test (`pm.test`) con el código esperado.
"""

from __future__ import annotations

import json
import uuid

from app.services.identificadores import nombre_campo_java
from app.services.modelo_relacional import Entidad, ModeloRelacional

_ESQUEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"

_EJEMPLOS = {
    "String": None,  # se usa el nombre del atributo
    "Integer": "1",
    "Long": "100",
    "Double": "1.5",
    "BigDecimal": "10.50",
    "Boolean": "true",
    "LocalDate": '"2025-01-15"',
    "LocalDateTime": '"2025-01-15T10:30:00"',
    "UUID": '"3fa85f64-5717-4562-b3fc-2c963f66afa6"',
}


def variable_id(e: Entidad) -> str:
    return nombre_campo_java(e.nombre_java) + "Id"


def _valor(tipo_java: str, nombre: str, sufijo: str) -> str:
    ejemplo = _EJEMPLOS.get(tipo_java)
    if ejemplo is None:
        return json.dumps(f"{nombre} {sufijo}".strip())
    return ejemplo


def _cuerpo(modelo: ModeloRelacional, e: Entidad, sufijo: str = "", id_roto: dict | None = None) -> str:
    lineas = []
    for a in modelo.atributos_totales(e.clase.id):
        lineas.append(f'  "{a.nombre_campo}": {_valor(a.tipo_java, a.nombre_campo, sufijo)}')
    for k in modelo.claves_de(e.clase.id, heredadas=True):
        ref = modelo.entidades[k.id_referida]
        if id_roto is not None and k is id_roto.get("clave"):
            lineas.append(f'  "{k.campo}": {{"id": 999999}}')
        elif k.obligatoria or not _depende_de(modelo, ref.clase.id, e.clase.id):
            lineas.append(f'  "{k.campo}": {{"id": {{{{{variable_id(ref)}}}}}}}')
    return "{\n" + ",\n".join(lineas) + "\n}"


def _depende_de(modelo: ModeloRelacional, a: str, b: str) -> bool:
    """True si `a` se crea después de `b` (referenciarla daría una variable vacía)."""
    orden = [x.clase.id for x in modelo.orden_creacion()]
    return orden.index(a) > orden.index(b)


def _test(codigo: int, guardar: list[str] | None = None) -> list[dict]:
    script = [f'pm.test("Status {codigo}", function () {{ pm.response.to.have.status({codigo}); }});']
    for var in guardar or []:
        script.append(f'if (pm.response.code === {codigo}) {{ pm.collectionVariables.set("{var}", pm.response.json().id); }}')
    return [{"listen": "test", "script": {"type": "text/javascript", "exec": script}}]


def _peticion(nombre: str, metodo: str, ruta: str, codigo: int, cuerpo: str | None = None, guardar=None) -> dict:
    segmentos = [s for s in ruta.strip("/").split("/") if s]
    req: dict = {
        "method": metodo,
        "header": [{"key": "Content-Type", "value": "application/json"}] if cuerpo else [],
        "url": {"raw": "{{baseUrl}}/" + "/".join(segmentos), "host": ["{{baseUrl}}"], "path": segmentos},
    }
    if cuerpo is not None:
        req["body"] = {"mode": "raw", "raw": cuerpo, "options": {"raw": {"language": "json"}}}
    return {"name": nombre, "event": _test(codigo, guardar), "request": req}


def generar_coleccion_postman(nombre_proyecto: str, modelo: ModeloRelacional) -> str:
    orden = modelo.orden_creacion()
    crud: list[dict] = []
    variables = {"baseUrl": "http://localhost:8080"}

    for e in orden:
        var = variable_id(e)
        variables[var] = ""
        base = f"api/{e.ruta}"
        carpeta: list[dict] = []
        if not e.abstracta:
            # Al crear una subclase, su id también vale para sus superclases.
            guardar = [var] + [variable_id(a) for a in modelo.ancestros(e.clase.id) if a.abstracta]
            carpeta.append(_peticion(f"Crear {e.nombre_java}", "POST", base, 201, _cuerpo(modelo, e), guardar))
        carpeta.append(_peticion(f"Listar {e.nombre_java}", "GET", base, 200))
        carpeta.append(_peticion(f"Obtener {e.nombre_java}", "GET", f"{base}/{{{{{var}}}}}", 200))
        if not e.abstracta:
            carpeta.append(
                _peticion(
                    f"Actualizar {e.nombre_java}", "PUT", f"{base}/{{{{{var}}}}}", 200, _cuerpo(modelo, e, "(editado)")
                )
            )
        carpeta.append(_peticion(f"Obtener {e.nombre_java} inexistente (404)", "GET", f"{base}/999999", 404))
        crud.append({"name": e.nombre_java, "item": carpeta})

    relaciones: list[dict] = []
    for m in modelo.muchos_a_muchos:
        dueño, inverso = modelo.entidades[m.id_dueño], modelo.entidades[m.id_inverso]
        if dueño.abstracta or inverso.abstracta:
            continue
        vd, vi = variable_id(dueño), variable_id(inverso)
        ruta_v = f"api/{dueño.ruta}/{{{{{vd}}}}}/{m.segmento_dueño}/{{{{{vi}}}}}"
        titulo = f"{dueño.nombre_java} *--* {inverso.nombre_java}"
        guardar_asoc = [variable_id(modelo.entidades[m.id_asociacion])] if m.id_asociacion else None
        items = []
        if m.id_asociacion:
            # El CRUD de la clase de asociación ya creó un vínculo para este par:
            # se desvincula primero y se vuelve a vincular por la ruta N:M.
            items.append(_peticion("Desvincular (204)", "DELETE", ruta_v, 204))
            items.append(_peticion("Vincular (201)", "POST", ruta_v, 201, guardar=guardar_asoc))
        else:
            items.append(_peticion("Vincular (201)", "POST", ruta_v, 201))
        items += [
            _peticion("Vincular de nuevo: ya existe (409)", "POST", ruta_v, 409),
            _peticion(
                f"Listar {inverso.nombre_java} de {dueño.nombre_java}",
                "GET",
                f"api/{dueño.ruta}/{{{{{vd}}}}}/{m.segmento_dueño}",
                200,
            ),
            _peticion(
                f"Listar {dueño.nombre_java} de {inverso.nombre_java}",
                "GET",
                f"api/{inverso.ruta}/{{{{{vi}}}}}/{m.segmento_inverso}",
                200,
            ),
        ]
        if not m.id_asociacion:
            items += [
                _peticion("Desvincular (204)", "DELETE", ruta_v, 204),
                _peticion("Volver a vincular (201)", "POST", ruta_v, 201),
            ]
        relaciones.append({"name": titulo, "item": items})

    integridad: list[dict] = []
    for e in orden:
        if e.abstracta:
            continue
        claves = [k for k in modelo.claves_de(e.clase.id, heredadas=True)]
        if not claves:
            continue
        integridad.append(
            _peticion(
                f"{e.nombre_java} con {claves[0].campo} inexistente (400)",
                "POST",
                f"api/{e.ruta}",
                400,
                _cuerpo(modelo, e, id_roto={"clave": claves[0]}),
            )
        )

    eliminar = [
        _peticion(f"Eliminar {e.nombre_java}", "DELETE", f"api/{e.ruta}/{{{{{variable_id(e)}}}}}", 204)
        for e in reversed(orden)
        if not e.abstracta
    ]

    coleccion = {
        "info": {
            "_postman_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"diagramador-uml/{nombre_proyecto}")),
            "name": f"{nombre_proyecto} — API generada",
            "description": (
                "Generada por Diagramador UML. Ejecutar la colección completa (Run) con el backend levantado "
                "en {{baseUrl}}: crea registros, prueba los vínculos N:M, la integridad referencial y borra."
            ),
            "schema": _ESQUEMA,
        },
        "item": [
            {"name": "1. CRUD", "item": crud},
            {"name": "2. Relaciones N:M", "item": relaciones},
            {"name": "3. Integridad referencial", "item": integridad},
            {"name": "4. Eliminar", "item": eliminar},
        ],
        "variable": [{"key": k, "value": v} for k, v in variables.items()],
    }
    return json.dumps(coleccion, ensure_ascii=False, indent=2)
