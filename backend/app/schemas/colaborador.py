from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.usuario import UsuarioOut


class ColaboradorAsignar(BaseModel):
    """CU05 — se agrega por id (resuelto vía la búsqueda de CU06), no por
    email: evita que alguien intente "invitar" a un email no registrado."""

    usuario_id: int


class ColaboradorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_proyecto: int
    id_usuario: int
    fecha_asignacion: datetime
    activo: bool
    usuario: UsuarioOut
