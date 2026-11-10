import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.usuario import Usuario
from app.routers.auth import get_current_user
from app.services.acceso import obtener_proyecto_propio
from app.services.diagrama import cargar_clases_y_relaciones
from app.services.generador_reporte import generar_pdf_reporte
from app.services.generador_spring import slug_paquete
from app.services.generador_xmi import generar_xmi_reporte

router = APIRouter(prefix="/proyectos/{proyecto_id}", tags=["reportes"])

_MEDIA_TYPE_POR_FORMATO = {
    "pdf": "application/pdf",
    "xmi": "application/xml",
}


@router.get("/reporte")
def obtener_reporte(
    proyecto_id: int,
    formato: Literal["pdf", "xmi"] = Query("pdf"),
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """CU07 - Genera un reporte del diagrama de clases del proyecto para
    descargar, en PDF (técnico, reportlab) o XMI (interoperabilidad con
    Enterprise Architect y otras herramientas UML, ver
    `app/services/generador_xmi.py`). A diferencia de CU08/CU09, solo el
    administrador dueño puede generarlo (los colaboradores no tienen
    acceso), por eso se usa `obtener_proyecto_propio` en vez del
    `obtener_proyecto_con_acceso` genérico."""
    proyecto = obtener_proyecto_propio(proyecto_id, usuario_actual, db)
    clases, relaciones = cargar_clases_y_relaciones(proyecto_id, db)
    if not clases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El proyecto no tiene contenido disponible para exportar. Agrega al menos una clase al diagrama.",
        )

    if formato == "pdf":
        contenido = generar_pdf_reporte(proyecto, clases, relaciones)
    else:
        contenido = generar_xmi_reporte(proyecto, clases, relaciones)
    nombre_archivo = f"{slug_paquete(proyecto.nombre)}-reporte.{formato}"

    return StreamingResponse(
        io.BytesIO(contenido),
        media_type=_MEDIA_TYPE_POR_FORMATO[formato],
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
