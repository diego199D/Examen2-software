"""Segundo parcial (RF-RT-01/02): grupos de trabajo.

Un usuario se registra con su nombre personal y el nombre de su grupo: si el
grupo ya existe (comparando sin mayúsculas/tildes/espacios extra) se une a
él; si no, se crea. Todos los integrantes de un grupo entran a los tableros
(proyectos) de cualquier miembro — es la "sala por grupo"."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.grupo import Grupo
from app.services.nombres import normalizar_nombre


def obtener_o_crear_grupo(nombre: str, db: Session) -> Grupo:
    nombre = " ".join(nombre.split())
    clave = normalizar_nombre(nombre)
    grupo = db.scalar(select(Grupo).where(Grupo.nombre_normalizado == clave))
    if grupo is None:
        grupo = Grupo(nombre=nombre, nombre_normalizado=clave)
        db.add(grupo)
        db.flush()
    return grupo
