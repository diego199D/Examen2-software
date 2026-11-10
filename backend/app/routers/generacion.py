import io

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.usuario import Usuario
from app.routers.auth import get_current_user
from app.schemas.generacion import GenerarFrontendInput
from app.services.acceso import obtener_proyecto_con_acceso, obtener_proyecto_propio
from app.services.diagrama import cargar_clases_y_relaciones
from app.services.generador_flutter import generar_zip_frontend
from app.services.generador_spring import generar_zip_backend, slug_paquete

router = APIRouter(prefix="/proyectos/{proyecto_id}", tags=["generacion"])


@router.post("/generar-backend")
def generar_backend(
    proyecto_id: int,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """CU08 - Genera un proyecto Maven de Spring Boot (entidades JPA,
    repositories, services y controllers REST) a partir del diagrama de
    clases guardado del proyecto, y lo devuelve como .zip descargable."""
    proyecto = obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)
    clases, relaciones = cargar_clases_y_relaciones(proyecto_id, db)
    if not clases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El proyecto no tiene clases en el diagrama todavía. Agrega al menos una antes de generar el backend.",
        )

    contenido_zip = generar_zip_backend(proyecto, clases, relaciones)
    nombre_archivo = f"{slug_paquete(proyecto.nombre)}-backend.zip"

    return StreamingResponse(
        io.BytesIO(contenido_zip),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.post("/generar-frontend")
def generar_frontend(
    proyecto_id: int,
    datos: GenerarFrontendInput,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """CU15 - Genera un proyecto Flutter (modelos, servicios HTTP con el
    paquete `http`, y pantallas de listado/formulario) a partir del mismo
    diagrama de clases guardado, apuntando al backend en `datos.url_base`
    (se asume que sigue la convención de rutas `/api/{plural}` que genera
    CU08), y lo devuelve como .zip descargable.

    A diferencia de CU08 (donde cualquiera con acceso al proyecto puede
    generar), la ficha de CU15 marca como único actor al Administrador —
    se usa `obtener_proyecto_propio` en vez del `obtener_proyecto_con_acceso`
    genérico, así que un colaborador recibe 403 acá aunque sí pueda generar
    el backend."""
    proyecto = obtener_proyecto_propio(proyecto_id, usuario_actual, db)
    clases, relaciones = cargar_clases_y_relaciones(proyecto_id, db)
    if not clases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El proyecto no tiene contenido disponible para exportar. Agrega al menos una clase al diagrama.",
        )

    contenido_zip = generar_zip_frontend(proyecto, clases, relaciones, datos.url_base)
    nombre_archivo = f"{slug_paquete(proyecto.nombre)}-frontend.zip"

    return StreamingResponse(
        io.BytesIO(contenido_zip),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
