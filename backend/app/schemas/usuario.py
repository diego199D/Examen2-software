from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.usuario import RolUsuario


class UsuarioBase(BaseModel):
    nombre_completo: str = Field(min_length=1, max_length=150)
    email: EmailStr


class UsuarioCreate(UsuarioBase):
    password: str = Field(min_length=8, max_length=72)
    rol: RolUsuario = RolUsuario.COLABORADOR


class UsuarioRegistro(BaseModel):
    nombre_completo: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UsuarioUpdate(BaseModel):
    nombre_completo: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    password_actual: str | None = None
    password_nuevo: str | None = Field(default=None, min_length=8, max_length=72)


class UsuarioOut(UsuarioBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rol: RolUsuario
    fecha_registro: datetime


class UsuarioBusquedaOut(BaseModel):
    """CU06 — resultado de búsqueda: sin `fecha_registro` (no aporta al
    flujo de elegir un colaborador y no hace falta exponerla ahí)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_completo: str
    email: EmailStr
    rol: RolUsuario


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
