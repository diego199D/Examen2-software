from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.atributo import VisibilidadMiembro


class Metodo(Base):
    __tablename__ = "metodos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id_clase: Mapped[str] = mapped_column(
        ForeignKey("clases_uml.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    parametros: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tipo_retorno: Mapped[str | None] = mapped_column(String(100), nullable=True)
    visibilidad: Mapped[VisibilidadMiembro] = mapped_column(
        Enum(VisibilidadMiembro), default=VisibilidadMiembro.PUBLICO, nullable=False
    )
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    clase = relationship("ClaseUml", back_populates="metodos")
