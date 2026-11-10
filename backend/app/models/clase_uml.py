from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.session import Base


class ClaseUml(Base):
    __tablename__ = "clases_uml"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id_proyecto: Mapped[int] = mapped_column(
        ForeignKey("proyectos.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    estereotipo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    es_abstracta: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pos_x: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    pos_y: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    atributos = relationship(
        "Atributo",
        back_populates="clase",
        cascade="all, delete-orphan",
        order_by="Atributo.orden",
    )
    metodos = relationship(
        "Metodo",
        back_populates="clase",
        cascade="all, delete-orphan",
        order_by="Metodo.orden",
    )
