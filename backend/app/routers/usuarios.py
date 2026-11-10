from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import hashear_password, verificar_password
from app.db.session import get_db
from app.models.proyecto_colaborador import ProyectoColaborador
from app.models.usuario import Usuario
from app.routers.auth import get_current_user
from app.schemas.usuario import UsuarioBusquedaOut, UsuarioOut, UsuarioUpdate
from app.services.acceso import obtener_proyecto_con_acceso

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("/me", response_model=UsuarioOut)
def leer_perfil(usuario_actual: Usuario = Depends(get_current_user)) -> Usuario:
    """CU03 - Ver el perfil del usuario autenticado."""
    return usuario_actual


@router.get("/buscar", response_model=list[UsuarioBusquedaOut])
def buscar_usuarios(
    q: str,
    proyecto_id: int | None = None,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Usuario]:
    """CU06 - Busca usuarios registrados por nombre o email (coincidencia
    parcial, sin distinguir mayúsculas). Nunca incluye a quien busca; si se
    pasa `proyecto_id`, tampoco a quienes ya son colaboradores activos de
    ese proyecto (para no repetir candidatos ya agregados en CU05).

    Si se pasa `proyecto_id`, exige que quien busca tenga acceso a ese
    proyecto (dueño o colaborador activo) — si no, 403. Sin este chequeo,
    alguien podría probar distintos `proyecto_id` para inferir quiénes son
    colaboradores de un proyecto ajeno a partir de qué usuarios desaparecen
    de los resultados."""
    if proyecto_id is not None:
        obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)

    termino = q.strip()
    if not termino:
        return []

    patron = f"%{termino}%"
    consulta = select(Usuario).where(
        Usuario.id != usuario_actual.id,
        or_(Usuario.nombre_completo.ilike(patron), Usuario.email.ilike(patron)),
    )

    if proyecto_id is not None:
        ya_colaboradores = select(ProyectoColaborador.id_usuario).where(
            ProyectoColaborador.id_proyecto == proyecto_id,
            ProyectoColaborador.activo.is_(True),
        )
        consulta = consulta.where(Usuario.id.notin_(ya_colaboradores))

    return list(db.scalars(consulta.order_by(Usuario.nombre_completo)))


@router.put("/me", response_model=UsuarioOut)
def actualizar_perfil(
    datos: UsuarioUpdate,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Usuario:
    """CU03 - Editar el perfil: nombre, email y (opcionalmente) contraseña."""
    if datos.nombre_completo is not None:
        usuario_actual.nombre_completo = datos.nombre_completo

    if datos.email is not None and datos.email != usuario_actual.email:
        existe = db.scalar(select(Usuario).where(Usuario.email == datos.email))
        if existe is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El email ya está registrado",
            )
        usuario_actual.email = datos.email

    if datos.password_nuevo is not None:
        if not datos.password_actual or not verificar_password(
            datos.password_actual, usuario_actual.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La contraseña actual es incorrecta",
            )
        usuario_actual.password_hash = hashear_password(datos.password_nuevo)

    db.commit()
    db.refresh(usuario_actual)
    return usuario_actual
