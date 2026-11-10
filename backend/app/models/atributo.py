import enum

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class VisibilidadMiembro(str, enum.Enum):
    PUBLICO = "PUBLICO"
    PRIVADO = "PRIVADO"
    PROTEGIDO = "PROTEGIDO"
    PAQUETE = "PAQUETE"


class Atributo(Base):
    __tablename__ = "atributos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id_clase: Mapped[str] = mapped_column(
        ForeignKey("clases_uml.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    visibilidad: Mapped[VisibilidadMiembro] = mapped_column(
        Enum(VisibilidadMiembro), default=VisibilidadMiembro.PRIVADO, nullable=False
    )
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    clase = relationship("ClaseUml", back_populates="atributos")
