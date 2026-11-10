from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.proyecto import Proyecto
from app.models.proyecto_colaborador import ProyectoColaborador
from app.models.usuario import Usuario


def obtener_proyecto_propio(proyecto_id: int, usuario: Usuario, db: Session) -> Proyecto:
    """Devuelve el proyecto solo si el usuario es su administrador dueño; si
    no, levanta 404 (no existe) o 403 (no es el dueño). Para operaciones que
    NO debe poder hacer un colaborador aunque tenga acceso de lectura
    (editar/eliminar proyecto, gestionar colaboradores — CU05)."""
    proyecto = db.get(Proyecto, proyecto_id)
    if proyecto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado",
        )
    if proyecto.id_administrador != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No eres el administrador de este proyecto",
        )
    return proyecto


def obtener_proyecto_con_acceso(proyecto_id: int, usuario: Usuario, db: Session) -> Proyecto:
    """Devuelve el proyecto si el usuario es su administrador o un colaborador
    activo; si no, levanta 404 (no existe) o 403 (sin acceso). Compartido por
    el router de diagramas (CU09) y el de generación de backend (CU08)."""
    proyecto = db.get(Proyecto, proyecto_id)
    if proyecto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado",
        )
    if proyecto.id_administrador == usuario.id:
        return proyecto

    es_colaborador = db.scalar(
        select(ProyectoColaborador).where(
            ProyectoColaborador.id_proyecto == proyecto_id,
            ProyectoColaborador.id_usuario == usuario.id,
            ProyectoColaborador.activo.is_(True),
        )
    )
    if es_colaborador is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este proyecto",
        )
    return proyecto
