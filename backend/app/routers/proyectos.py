from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.proyecto import Proyecto
from app.models.proyecto_colaborador import ProyectoColaborador
from app.models.usuario import RolUsuario, Usuario
from app.routers.auth import get_current_user
from app.schemas.proyecto import ProyectoCreate, ProyectoOut, ProyectoUpdate
from app.services.acceso import obtener_proyecto_propio

router = APIRouter(prefix="/proyectos", tags=["proyectos"])


def _nombre_duplicado(
    nombre: str, id_administrador: int, db: Session, excluir_id: int | None = None
) -> bool:
    consulta = select(Proyecto).where(
        Proyecto.id_administrador == id_administrador,
        Proyecto.nombre == nombre,
    )
    if excluir_id is not None:
        consulta = consulta.where(Proyecto.id != excluir_id)
    return db.scalar(consulta) is not None


@router.get("", response_model=list[ProyectoOut])
def listar_proyectos(
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Proyecto]:
    """CU04 - Lista los proyectos propios y aquellos donde el usuario colabora."""
    propios = list(
        db.scalars(select(Proyecto).where(Proyecto.id_administrador == usuario_actual.id))
    )
    for proyecto in propios:
        proyecto.rol_en_proyecto = RolUsuario.ADMINISTRADOR

    colaborados = list(
        db.scalars(
            select(Proyecto)
            .join(ProyectoColaborador, ProyectoColaborador.id_proyecto == Proyecto.id)
            .where(
                ProyectoColaborador.id_usuario == usuario_actual.id,
                ProyectoColaborador.activo.is_(True),
            )
        )
    )
    for proyecto in colaborados:
        proyecto.rol_en_proyecto = RolUsuario.COLABORADOR

    return sorted(propios + colaborados, key=lambda p: p.fecha_creacion, reverse=True)


@router.post("", response_model=ProyectoOut, status_code=status.HTTP_201_CREATED)
def crear_proyecto(
    datos: ProyectoCreate,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Proyecto:
    """CU04 - Crea un proyecto. El nombre debe ser único por administrador."""
    if _nombre_duplicado(datos.nombre, usuario_actual.id, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya tienes un proyecto con ese nombre",
        )
    proyecto = Proyecto(
        nombre=datos.nombre,
        descripcion=datos.descripcion,
        id_administrador=usuario_actual.id,
    )
    db.add(proyecto)
    db.commit()
    db.refresh(proyecto)
    proyecto.rol_en_proyecto = RolUsuario.ADMINISTRADOR
    return proyecto


@router.put("/{proyecto_id}", response_model=ProyectoOut)
def actualizar_proyecto(
    proyecto_id: int,
    datos: ProyectoUpdate,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Proyecto:
    """CU04 - Edita un proyecto propio."""
    proyecto = obtener_proyecto_propio(proyecto_id, usuario_actual, db)

    if datos.nombre is not None and datos.nombre != proyecto.nombre:
        if _nombre_duplicado(datos.nombre, usuario_actual.id, db, excluir_id=proyecto.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya tienes un proyecto con ese nombre",
            )
        proyecto.nombre = datos.nombre

    if datos.descripcion is not None:
        proyecto.descripcion = datos.descripcion

    db.commit()
    db.refresh(proyecto)
    proyecto.rol_en_proyecto = RolUsuario.ADMINISTRADOR
    return proyecto


@router.delete("/{proyecto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_proyecto(
    proyecto_id: int,
    confirmar: bool = False,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """CU04 - Elimina un proyecto propio.

    Si tiene colaboradores activos, exige `?confirmar=true`; si no, responde 409.
    """
    proyecto = obtener_proyecto_propio(proyecto_id, usuario_actual, db)

    colaboradores_activos = db.scalar(
        select(func.count())
        .select_from(ProyectoColaborador)
        .where(
            ProyectoColaborador.id_proyecto == proyecto.id,
            ProyectoColaborador.activo.is_(True),
        )
    )
    if colaboradores_activos and not confirmar:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"El proyecto tiene {colaboradores_activos} colaborador(es) activo(s). "
                "Repite la petición con ?confirmar=true para eliminarlo de todos modos."
            ),
        )

    db.delete(proyecto)
    db.commit()
