from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.usuario import Usuario
from app.routers.auth import get_current_user
from app.schemas.reconocimiento_foto import ConfirmarReconocimientoResultado, ReconocimientoFotoResultado
from app.services.acceso import obtener_proyecto_con_acceso
from app.services.comandos_voz import ComandoVozNoDisponibleError
from app.services.reconocimiento_foto import ImagenInvalidaError, aplicar_reconocimiento, reconocer_diagrama

router = APIRouter(prefix="/proyectos/{proyecto_id}/reconocimiento-foto", tags=["reconocimiento-foto"])


@router.post("", response_model=ReconocimientoFotoResultado)
async def reconocer_foto_endpoint(
    proyecto_id: int,
    archivo: UploadFile = File(...),
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReconocimientoFotoResultado:
    """CU12 - Interpreta una foto/captura de un diagrama de clases con visión
    de OpenAI y devuelve la vista previa (clases/atributos/relaciones
    detectadas) SIN aplicarla al proyecto todavía -- ver
    POST .../confirmar."""
    obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)
    contenido = await archivo.read()
    try:
        return reconocer_diagrama(contenido, archivo.content_type)
    except ImagenInvalidaError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
    except ComandoVozNoDisponibleError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de reconocimiento de imágenes no está disponible en este momento. Intenta de nuevo en unos segundos.",
        ) from err


@router.post("/confirmar", response_model=ConfirmarReconocimientoResultado)
def confirmar_reconocimiento_endpoint(
    proyecto_id: int,
    datos: ReconocimientoFotoResultado,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfirmarReconocimientoResultado:
    """CU12 - Aplica la vista previa (ya revisada/editada por el usuario en
    el frontend) al diagrama del proyecto -- AGREGA las clases/relaciones a
    las que ya existan, no exige que el diagrama esté vacío (a diferencia de
    la importación XMI de CU09)."""
    obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)
    try:
        return aplicar_reconocimiento(proyecto_id, datos, db)
    except ImagenInvalidaError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
