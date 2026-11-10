from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.proyecto_colaborador import ProyectoColaborador
from app.models.usuario import Usuario
from app.routers.auth import get_current_user
from app.schemas.colaborador import ColaboradorAsignar, ColaboradorOut
from app.services.acceso import obtener_proyecto_con_acceso, obtener_proyecto_propio

router = APIRouter(prefix="/proyectos/{proyecto_id}/colaboradores", tags=["colaboradores"])


@router.get("", response_model=list[ColaboradorOut])
def listar_colaboradores(
    proyecto_id: int,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProyectoColaborador]:
    """CU05 - Lista los colaboradores activos del proyecto. Visible al
    administrador dueño o a cualquier colaborador activo (no solo al dueño)."""
    obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)
    return list(
        db.scalars(
            select(ProyectoColaborador).where(
                ProyectoColaborador.id_proyecto == proyecto_id,
                ProyectoColaborador.activo.is_(True),
            )
        )
    )


@router.post("", response_model=ColaboradorOut, status_code=status.HTTP_201_CREATED)
def agregar_colaborador(
    proyecto_id: int,
    datos: ColaboradorAsignar,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProyectoColaborador:
    """CU05 - Agrega (o reactiva) un colaborador por id de usuario ya
    registrado (resuelto vía la búsqueda de CU06). Solo el administrador
    dueño del proyecto puede hacerlo — un colaborador existente no, aunque
    tenga acceso de lectura."""
    proyecto = obtener_proyecto_propio(proyecto_id, usuario_actual, db)

    if datos.usuario_id == usuario_actual.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes agregarte a ti mismo como colaborador de tu propio proyecto",
        )

    usuario_colaborador = db.get(Usuario, datos.usuario_id)
    if usuario_colaborador is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe un usuario registrado con ese id",
        )

    colaborador = db.scalar(
        select(ProyectoColaborador).where(
            ProyectoColaborador.id_proyecto == proyecto.id,
            ProyectoColaborador.id_usuario == usuario_colaborador.id,
        )
    )
    if colaborador is not None:
        if colaborador.activo:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ese usuario ya es colaborador del proyecto",
            )
        # Reactivar en vez de crear otra fila: la constraint única
        # (id_proyecto, id_usuario) no permite duplicados.
        colaborador.activo = True
        colaborador.fecha_asignacion = func.now()
    else:
        colaborador = ProyectoColaborador(
            id_proyecto=proyecto.id,
            id_usuario=usuario_colaborador.id,
            activo=True,
        )
        db.add(colaborador)

    db.commit()
    db.refresh(colaborador)
    return colaborador


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def quitar_colaborador(
    proyecto_id: int,
    usuario_id: int,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """CU05 - Quita (soft delete: activo=false) a un colaborador del
    proyecto. Solo el administrador dueño. La fila no se borra: conserva el
    historial y no rompe la validación de "colaboradores activos" al
    eliminar el proyecto (CU04)."""
    proyecto = obtener_proyecto_propio(proyecto_id, usuario_actual, db)

    colaborador = db.scalar(
        select(ProyectoColaborador).where(
            ProyectoColaborador.id_proyecto == proyecto.id,
            ProyectoColaborador.id_usuario == usuario_id,
            ProyectoColaborador.activo.is_(True),
        )
    )
    if colaborador is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Colaborador no encontrado en este proyecto",
        )

    colaborador.activo = False
    db.commit()
