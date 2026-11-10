"""Mapeo de tipos UML (texto libre en `Atributo.tipo`) a Java y SQL.

Compartido por el generador Spring Boot (CU08), el DDL exportado y el
modelo relacional. Explícito y documentado, con un valor por defecto
seguro (String / VARCHAR) para tipos no reconocidos.
"""

from __future__ import annotations

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

# Tipo SQL (dialecto PostgreSQL; H2 en modo PostgreSQL acepta los mismos)
# para cada tipo Java del mapeo de arriba.
TIPOS_SQL: dict[str, str] = {
    "String": "VARCHAR(255)",
    "Integer": "INTEGER",
    "Long": "BIGINT",
    "Double": "DOUBLE PRECISION",
    "BigDecimal": "NUMERIC(19, 2)",
    "Boolean": "BOOLEAN",
    "LocalDate": "DATE",
    "LocalDateTime": "TIMESTAMP",
    "UUID": "UUID",
}


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


def tipo_sql(tipo_java: str) -> str:
    return TIPOS_SQL.get(tipo_java, "VARCHAR(255)")
