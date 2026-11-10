from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.usuario import Usuario
from app.routers.auth import get_current_user
from app.schemas.agente import AgenteInput, AgenteRespuesta
from app.services.acceso import obtener_proyecto_con_acceso
from app.services.agente import responder_mensaje
from app.services.comandos_voz import ComandoVozNoDisponibleError

router = APIRouter(prefix="/proyectos/{proyecto_id}/agente", tags=["agente"])


@router.post("", response_model=AgenteRespuesta)
def conversar_con_agente_endpoint(
    proyecto_id: int,
    datos: AgenteInput,
    usuario_actual: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgenteRespuesta:
    """CU13 - Conversa con el agente integrado: ejecuta una de las 5 acciones
    de CU11 si el mensaje es una instrucción de edición clara, o responde en
    texto (pregunta, aclaración, "no entendí") sin tocar el diagrama en
    cualquier otro caso -- a diferencia de CU11 acá "no se pudo interpretar"
    nunca es un error HTTP, es una respuesta conversacional normal."""
    obtener_proyecto_con_acceso(proyecto_id, usuario_actual, db)
    try:
        return responder_mensaje(proyecto_id, datos.historial, datos.mensaje, db)
    except ComandoVozNoDisponibleError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El agente no está disponible en este momento. Intenta de nuevo en unos segundos.",
        ) from err
