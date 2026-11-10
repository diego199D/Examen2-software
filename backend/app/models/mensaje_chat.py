import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


class TipoMensaje(str, enum.Enum):
    HUMANO = "humano"
    SENIOR_AI = "senior_ai"
    SISTEMA = "sistema"


class MensajeChat(Base):
    """Segundo parcial (RF-IA): chat grupal único y público de la sala de un
    proyecto, persistido para que la conversación sobreviva a que todos se
    desconecten. `datos` guarda, para los mensajes del Senior, la propuesta
    de cambios al diagrama y su estado (pendiente/aplicada/rechazada)."""

    __tablename__ = "mensajes_chat"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_proyecto: Mapped[int] = mapped_column(ForeignKey("proyectos.id", ondelete="CASCADE"), nullable=False, index=True)
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    autor_nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    tipo: Mapped[TipoMensaje] = mapped_column(
        Enum(TipoMensaje, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    datos: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
