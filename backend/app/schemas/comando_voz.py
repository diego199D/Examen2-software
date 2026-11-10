"""Schemas de CU11 (comandos de voz): la "acción estructurada" que
`app/services/comandos_voz.py` devuelve luego de interpretar un comando con
OpenAI function calling. Los ids ya vienen resueltos (nunca nombres crudos) y
nunca se inventa un `id` nuevo acá -- eso lo sigue generando el cliente con
`crypto.randomUUID()`, igual que hoy para cualquier clase/atributo/relación
creada a mano (ver `useDiagrama.ts`)."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.models.atributo import VisibilidadMiembro
from app.models.relacion import TipoRelacion


class ComandoVozInput(BaseModel):
    # 2000 y no 500: la escucha continua (CU11) permite dictar varias clases y
    # sus relaciones en un solo comando.
    texto: str = Field(min_length=1, max_length=2000)


class AtributoNuevoIO(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    tipo: str | None = Field(default=None, max_length=100)
    visibilidad: VisibilidadMiembro = VisibilidadMiembro.PRIVADO


class AccionCrearClase(BaseModel):
    accion: Literal["crear_clase"] = "crear_clase"
    nombre_clase: str
    atributos: list[AtributoNuevoIO] = []
    resumen: str


class AccionAgregarAtributo(BaseModel):
    accion: Literal["agregar_atributo"] = "agregar_atributo"
    id_clase: str
    nombre_clase: str
    atributo: AtributoNuevoIO
    resumen: str


class AccionEliminarClase(BaseModel):
    accion: Literal["eliminar_clase"] = "eliminar_clase"
    id_clase: str
    nombre_clase: str
    resumen: str


class AccionCrearRelacion(BaseModel):
    accion: Literal["crear_relacion"] = "crear_relacion"
    id_clase_origen: str
    id_clase_destino: str
    nombre_clase_origen: str
    nombre_clase_destino: str
    tipo: TipoRelacion
    multiplicidad_origen: str | None = None
    multiplicidad_destino: str | None = None
    resumen: str


class ClaseNuevaIO(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    atributos: list[AtributoNuevoIO] = []


class AtributosAgregadosIO(BaseModel):
    id_clase: str
    nombre_clase: str
    atributos: list[AtributoNuevoIO]


class ExtremoRelacionIO(BaseModel):
    """Un extremo de una relación de `AccionModificarDiagrama`: `id_clase` si
    la clase ya existe en el diagrama, o `None` si es una de las
    `clases_nuevas` del mismo comando -- su id todavía no existe (lo genera el
    frontend), así que el frontend la resuelve por `nombre_clase`."""

    id_clase: str | None = None
    nombre_clase: str


class RelacionNuevaIO(BaseModel):
    origen: ExtremoRelacionIO
    destino: ExtremoRelacionIO
    tipo: TipoRelacion
    multiplicidad_origen: str | None = None
    multiplicidad_destino: str | None = None
    etiqueta: str | None = None


class AccionModificarDiagrama(BaseModel):
    """CU11 — un comando de voz en lenguaje natural puede crear varias clases,
    agregar atributos a clases existentes y relacionarlas (con tipo y
    multiplicidad deducidos) de una sola vez. `advertencias` lista lo que se
    descartó o ajustó, sin hacer fallar el comando entero."""

    accion: Literal["modificar_diagrama"] = "modificar_diagrama"
    clases_nuevas: list[ClaseNuevaIO] = []
    atributos_agregados: list[AtributosAgregadosIO] = []
    relaciones: list[RelacionNuevaIO] = []
    advertencias: list[str] = []
    resumen: str


class AccionRenombrarClase(BaseModel):
    accion: Literal["renombrar_clase"] = "renombrar_clase"
    id_clase: str
    nombre_anterior: str
    nombre_nuevo: str
    resumen: str


AccionVoz = Annotated[
    Union[
        AccionCrearClase,
        AccionAgregarAtributo,
        AccionEliminarClase,
        AccionCrearRelacion,
        AccionRenombrarClase,
        AccionModificarDiagrama,
    ],
    Field(discriminator="accion"),
]
