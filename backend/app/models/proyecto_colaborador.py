from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.session import Base


class ProyectoColaborador(Base):
    __tablename__ = "proyecto_colaboradores"
    __table_args__ = (
        UniqueConstraint("id_proyecto", "id_usuario", name="uq_proyecto_colaborador"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    id_proyecto: Mapped[int] = mapped_column(ForeignKey("proyectos.id"), nullable=False)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha_asignacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    proyecto = relationship("Proyecto", back_populates="colaboradores")
    usuario = relationship("Usuario")