import enum

from sqlalchemy import Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TipoRelacion(str, enum.Enum):
    ASOCIACION = "ASOCIACION"
    HERENCIA = "HERENCIA"
    AGREGACION = "AGREGACION"
    COMPOSICION = "COMPOSICION"


class Relacion(Base):
    __tablename__ = "relaciones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id_proyecto: Mapped[int] = mapped_column(
        ForeignKey("proyectos.id", ondelete="CASCADE"), nullable=False
    )
    id_clase_origen: Mapped[str] = mapped_column(
        ForeignKey("clases_uml.id", ondelete="CASCADE"), nullable=False
    )
    id_clase_destino: Mapped[str] = mapped_column(
        ForeignKey("clases_uml.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[TipoRelacion] = mapped_column(Enum(TipoRelacion), nullable=False)
    etiqueta: Mapped[str | None] = mapped_column(String(100), nullable=True)
    multiplicidad_origen: Mapped[str | None] = mapped_column(String(20), nullable=True)
    multiplicidad_destino: Mapped[str | None] = mapped_column(String(20), nullable=True)
    handle_origen: Mapped[str | None] = mapped_column(String(10), nullable=True)
    handle_destino: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Solo visuales (el lienzo), ningún generador/exportador los usa:
    # `forma` es RECTA | L | CURVA (null = RECTA) y `desvio_x`/`desvio_y` es
    # el corrimiento del punto de control arrastrable RESPECTO DEL PUNTO
    # MEDIO entre los dos extremos (no una posición absoluta -- así, si se
    # mueve una clase, la línea conserva su forma). Ver RelacionEdge.tsx.
    forma: Mapped[str | None] = mapped_column(String(10), nullable=True)
    desvio_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    desvio_y: Mapped[float | None] = mapped_column(Float, nullable=True)

    origen = relationship("ClaseUml", foreign_keys=[id_clase_origen])
    destino = relationship("ClaseUml", foreign_keys=[id_clase_destino])
