from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.atributo import VisibilidadMiembro
from app.models.relacion import TipoRelacion


class AtributoIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str = Field(min_length=1, max_length=100)
    tipo: str | None = Field(default=None, max_length=100)
    visibilidad: VisibilidadMiembro = VisibilidadMiembro.PRIVADO
    orden: int = 0


class MetodoIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str = Field(min_length=1, max_length=100)
    parametros: str | None = Field(default=None, max_length=255)
    tipo_retorno: str | None = Field(default=None, max_length=100)
    visibilidad: VisibilidadMiembro = VisibilidadMiembro.PUBLICO
    orden: int = 0


class ClaseIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str = Field(min_length=1, max_length=150)
    estereotipo: str | None = Field(default=None, max_length=50)
    es_abstracta: bool = False
    pos_x: float = 0
    pos_y: float = 0
    atributos: list[AtributoIO] = []
    metodos: list[MetodoIO] = []


class RelacionIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    id_clase_origen: str
    id_clase_destino: str
    tipo: TipoRelacion
    etiqueta: str | None = None
    multiplicidad_origen: str | None = None
    multiplicidad_destino: str | None = None
    handle_origen: str | None = None
    handle_destino: str | None = None
    # Solo visuales -- ver el comentario en `app/models/relacion.py`.
    forma: Literal["RECTA", "L", "CURVA"] | None = None
    desvio_x: float | None = None
    desvio_y: float | None = None


class DiagramaIO(BaseModel):
    clases: list[ClaseIO] = []
    relaciones: list[RelacionIO] = []


class ImportacionXmiResultado(BaseModel):
    """Respuesta de `POST /proyectos/{id}/diagrama/importar-xmi` (CU09): el
    diagrama ya guardado, más cualquier advertencia de cosas del archivo que
    no se pudieron interpretar del todo (ver `app/services/importador_xmi.py`)
    -- no son errores fatales, el import se completó igual."""

    diagrama: DiagramaIO
    advertencias: list[str] = []
