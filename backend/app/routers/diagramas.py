from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.usuario import Usuario
from app.routers.auth import get_current_user
from app.schemas.diagrama import DiagramaIO, ImportacionXmiResultado
from app.services.acceso import obtener_proyecto_con_acceso
from app.services.diagrama import cargar_clases_y_relaciones, cargar_diagrama, guardar_diagrama
from app.services.importador_xmi import XmiInvalidoError, importar_xmi

router = APIRouter(prefix="/proyectos/{proyecto_id}/diagrama", tags=["diagrama"])


@router.get("", response_model=DiagramaIO)
def obtener_diagrama(
    proyecto_id: int,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiagramaIO:
    """CU09 - Obtiene el diagrama de clases de un proyecto propio o colaborado."""
    obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)
    return cargar_diagrama(proyecto_id, db)


@router.put("", response_model=DiagramaIO)
def guardar_diagrama_endpoint(
    proyecto_id: int,
    datos: DiagramaIO,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiagramaIO:
    """CU09 - Reemplaza el diagrama completo del proyecto (autoguardado)."""
    obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)
    guardar_diagrama(proyecto_id, datos, db)
    return cargar_diagrama(proyecto_id, db)


@router.post("/importar-xmi", response_model=ImportacionXmiResultado)
async def importar_xmi_endpoint(
    proyecto_id: int,
    archivo: UploadFile = File(...),
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportacionXmiResultado:
    """CU09 - Importa un archivo .xmi (UML2/XMI 2.1, ver
    `app/services/importador_xmi.py`) como el diagrama de clases del
    proyecto. Solo se admite sobre un diagrama todavía vacío -- 409 si el
    proyecto ya tiene clases (no hay fusión ni reemplazo automático, hay que
    vaciarlo a mano primero). 400 si el archivo no es XML válido o no
    contiene ninguna clase UML reconocible."""
    obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)

    clases_existentes, _ = cargar_clases_y_relaciones(proyecto_id, db)
    if clases_existentes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El proyecto ya tiene clases en su diagrama. Elimínalas manualmente antes de "
                "importar un XMI (no se admite fusión ni reemplazo automático)."
            ),
        )

    contenido = await archivo.read()
    try:
        resultado = importar_xmi(contenido)
    except XmiInvalidoError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

    guardar_diagrama(proyecto_id, resultado.diagrama, db)
    return ImportacionXmiResultado(diagrama=cargar_diagrama(proyecto_id, db), advertencias=resultado.advertencias)
