"""Schemas de CU12 (reconocimiento de diagrama por fotografía).

`ReconocimientoFotoResultado` es la "vista previa" que devuelve el endpoint
de reconocimiento (POST .../reconocimiento-foto) y también el body que
recibe el endpoint de confirmación (POST .../reconocimiento-foto/confirmar)
-- el usuario puede revisar/editar ese JSON en el frontend antes de
confirmarlo, mismo criterio que ya usa CU13 con `AccionVoz`."""

from pydantic import BaseModel, Field, model_validator

from app.models.relacion import TipoRelacion
from app.schemas.diagrama import DiagramaIO


def _limpiar_miembro(datos, campo_tipo: str):
    """El modelo de visión a veces copia la notación UML tal cual dentro del
    nombre ("- nombre", "+ getTotal()", "edad: int"): se limpia en código
    para no guardar un atributo llamado "- nombre"."""
    if not isinstance(datos, dict) or not isinstance(datos.get("nombre"), str):
        return datos
    nombre = datos["nombre"].strip().lstrip("+-#~ ").strip()
    if ":" in nombre:
        nombre, _, tipo = nombre.partition(":")
        if not datos.get(campo_tipo) and tipo.strip():
            datos = {**datos, campo_tipo: tipo.strip()}
        nombre = nombre.strip()
    if nombre.endswith(")") and "(" in nombre:
        nombre = nombre[: nombre.index("(")].strip()
    return {**datos, "nombre": nombre or datos["nombre"].strip()}


class AtributoDetectadoIO(BaseModel):
    nombre: str
    tipo: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _limpiar(cls, datos):
        return _limpiar_miembro(datos, "tipo")


class MetodoDetectadoIO(BaseModel):
    nombre: str
    tipo_retorno: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _limpiar(cls, datos):
        return _limpiar_miembro(datos, "tipo_retorno")


class ClaseDetectadaIO(BaseModel):
    nombre: str
    atributos: list[AtributoDetectadoIO] = []
    metodos: list[MetodoDetectadoIO] = []


class RelacionDetectadaIO(BaseModel):
    clase_origen: str
    clase_destino: str
    tipo: TipoRelacion
    # Texto escrito en medio de la línea (ej. "emplea"), o None.
    etiqueta: str | None = None
    multiplicidad_origen: str | None = None
    multiplicidad_destino: str | None = None
    # Campo redundante para corregir la dirección de relaciones dirigidas
    # sin depender de que el modelo ordene bien clase_origen/clase_destino
    # (ver _corregir_direccion_por_extremo_marcado en reconocimiento_foto.py):
    # para HERENCIA, la clase donde está el triángulo hueco (la superclase);
    # para AGREGACION/COMPOSICION, la clase donde está el rombo (el "todo");
    # None para ASOCIACION.
    clase_extremo_marcado: str | None = None


class ReconocimientoFotoResultado(BaseModel):
    reconocido: bool
    mensaje: str
    clases: list[ClaseDetectadaIO] = Field(default_factory=list)
    relaciones: list[RelacionDetectadaIO] = Field(default_factory=list)
    # Correcciones que el backend hizo solo sobre lo que devolvió el modelo
    # (p. ej. una composición sin rombo dibujado bajada a asociación) -- se
    # muestran en la vista previa. Informativo: la confirmación lo ignora.
    advertencias: list[str] = Field(default_factory=list)


class ConfirmarReconocimientoResultado(BaseModel):
    """Mismo shape que `ImportacionXmiResultado` (CU09) a propósito -- el
    frontend reusa el mismo manejo (`diagrama.importarDiagrama`)."""

    diagrama: DiagramaIO
    advertencias: list[str] = []
