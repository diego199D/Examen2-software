"""Identificadores (clase/campo/tabla/ruta/paquete) a partir de los nombres
UML libres que escribe el usuario. Transformaciones agnósticas del lenguaje
compartidas por todos los generadores (Spring, DDL, Postman, Flutter): TIENEN
que dar el mismo resultado en todos, o las rutas/columnas no coinciden.
"""

from __future__ import annotations

import re
import unicodedata


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
