from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.session import Base


class Proyecto(Base):
    __tablename__ = "proyectos"
    __table_args__ = (
        UniqueConstraint("id_administrador", "nombre", name="uq_proyecto_nombre_por_admin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    id_administrador: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)

    administrador = relationship("Usuario", back_populates="proyectos_administrados")
    colaboradores = relationship(
        "ProyectoColaborador", back_populates="proyecto", cascade="all, delete-orphan"
    )
    clases = relationship("ClaseUml", cascade="all, delete-orphan")