"""Schemas de CU13 (agente conversacional). Reutiliza `AccionVoz` de
`app/schemas/comando_voz.py` (CU11) tal cual -- misma unión discriminada de
5 acciones, no se duplica."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.comando_voz import AccionVoz


class MensajeChatIO(BaseModel):
    rol: Literal["usuario", "agente"]
    texto: str = Field(min_length=1, max_length=1000)


class AgenteInput(BaseModel):
    mensaje: str = Field(min_length=1, max_length=1000)
    historial: list[MensajeChatIO] = Field(default_factory=list, max_length=40)


class AgenteRespuesta(BaseModel):
    texto: str
    accion: AccionVoz | None = None
