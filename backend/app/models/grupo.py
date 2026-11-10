from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


class Grupo(Base):
    """Segundo parcial (RF-RT): grupo de trabajo. Cada usuario se registra
    con su nombre personal y el nombre de su grupo; los integrantes de un
    grupo comparten los tableros (proyectos) de todos sus miembros."""

    __tablename__ = "grupos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    # Para que "Grupo 7" y "grupo  7" sean el mismo grupo (ver services/grupos.py).
    nombre_normalizado: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
