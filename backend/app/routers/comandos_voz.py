from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.usuario import Usuario
from app.routers.auth import get_current_user
from app.schemas.comando_voz import AccionVoz, ComandoVozInput
from app.services.acceso import obtener_proyecto_con_acceso
from app.services.comandos_voz import (
    ComandoVozInvalidoError,
    ComandoVozNoDisponibleError,
    interpretar_comando,
)

router = APIRouter(prefix="/proyectos/{proyecto_id}/comandos-voz", tags=["comandos-voz"])


@router.post("", response_model=AccionVoz)
def interpretar_comando_voz_endpoint(
    proyecto_id: int,
    datos: ComandoVozInput,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccionVoz:
    """CU11 - Interpreta un comando de voz ya transcrito (texto) y devuelve la
    acción estructurada correspondiente, con ids ya resueltos contra el
    diagrama actual. No persiste nada -- el frontend aplica la acción con las
    funciones ya existentes de `useDiagrama.ts`."""
    obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)
    try:
        return interpretar_comando(proyecto_id, datos.texto, db)
    except ComandoVozInvalidoError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except ComandoVozNoDisponibleError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de interpretación de voz no está disponible en este momento. Intenta de nuevo en unos segundos.",
        ) from err
