import enum
from datetime import datetime

from sqlalchemy import String, Enum, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.session import Base


class RolUsuario(str, enum.Enum):
    ADMINISTRADOR = "ADMINISTRADOR"
    COLABORADOR = "COLABORADOR"


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(Enum(RolUsuario), nullable=False)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Segundo parcial: grupo de trabajo (nullable: usuarios previos al cambio).
    id_grupo: Mapped[int | None] = mapped_column(ForeignKey("grupos.id", ondelete="SET NULL"), nullable=True)
    grupo = relationship("Grupo", lazy="joined")

    @property
    def nombre_grupo(self) -> str | None:
        return self.grupo.nombre if self.grupo is not None else None

    proyectos_administrados = relationship(
        "Proyecto", back_populates="administrador", cascade="all, delete-orphan"
    )