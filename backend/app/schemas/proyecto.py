from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.usuario import RolUsuario


class ProyectoBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    descripcion: str | None = None


class ProyectoCreate(ProyectoBase):
    pass


class ProyectoUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    descripcion: str | None = None


class ProyectoOut(ProyectoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_administrador: int
    fecha_creacion: datetime
    rol_en_proyecto: RolUsuario
