"""CU10 - WebSocket de colaboración en tiempo real sobre el diagrama de
clases (Yjs). El estado compartido y el guardado con debounce viven en
app/services/yjs_rooms.py; acá solo se resuelve autenticación/acceso antes
de aceptar la conexión y se conecta el WebSocket al room correspondiente."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.security import decodificar_access_token
from app.db.session import get_db
from app.models.usuario import Usuario
from app.services import yjs_rooms
from app.services.acceso import obtener_proyecto_con_acceso

router = APIRouter(tags=["diagrama-colaborativo"])

# Códigos de cierre privados (rango 4000-4999 de RFC 6455), usados para
# rechazar el handshake ANTES de aceptarlo — el navegador los recibe en el
# evento `close` del WebSocket nativo.
CIERRE_SIN_TOKEN = 4401
CIERRE_PROYECTO_NO_ENCONTRADO = 4404
CIERRE_SIN_ACCESO = 4403


def _usuario_desde_token(token: str | None, db: Session) -> Usuario | None:
    """Los WebSockets del navegador no permiten headers Authorization
    personalizados, así que el JWT llega como query param (?token=...) en
    vez de vía el esquema OAuth2 que usa get_current_user en los endpoints
    HTTP."""
    if not token:
        return None
    sub = decodificar_access_token(token)
    if sub is None:
        return None
    try:
        usuario_id = int(sub)
    except ValueError:
        return None
    return db.get(Usuario, usuario_id)


class FastAPIChannel:
    """Adapta un WebSocket de FastAPI/Starlette al protocolo `pycrdt.Channel`
    (path/send/recv/__aiter__) que espera `YRoom.serve()`. Calcado del
    `HttpxWebsocket` que trae pycrdt.websocket de fábrica (pycrdt/websocket/
    websocket.py) — Starlette expone los mismos send_bytes/receive_bytes."""

    def __init__(self, websocket: WebSocket, path: str) -> None:
        self._websocket = websocket
        self._path = path
        self._send_lock = asyncio.Lock()

    @property
    def path(self) -> str:
        return self._path

    def __aiter__(self) -> "FastAPIChannel":
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self.recv()
        except Exception:
            raise StopAsyncIteration()

    async def send(self, message: bytes) -> None:
        async with self._send_lock:
            await self._websocket.send_bytes(message)

    async def recv(self) -> bytes:
        data = await self._websocket.receive_bytes()
        return bytes(data)


@router.websocket("/ws/proyectos/{proyecto_id}/diagrama")
async def ws_diagrama(
    websocket: WebSocket,
    proyecto_id: int,
    token: str | None = None,
    db: Session = Depends(get_db),
) -> None:
    usuario = _usuario_desde_token(token, db)
    if usuario is None:
        await websocket.close(code=CIERRE_SIN_TOKEN)
        return

    try:
        obtener_proyecto_con_acceso(proyecto_id, usuario, db)
    except HTTPException as exc:
        codigo = CIERRE_PROYECTO_NO_ENCONTRADO if exc.status_code == 404 else CIERRE_SIN_ACCESO
        await websocket.close(code=codigo)
        return

    await websocket.accept()

    sala = await yjs_rooms.gestor_salas.conectar(proyecto_id)
    canal = FastAPIChannel(websocket, path=f"/proyectos/{proyecto_id}/diagrama")
    try:
        await sala.yroom.serve(canal)
    except WebSocketDisconnect:
        pass
    finally:
        # `shield`: si esta tarea se cancela porque el cliente cortó la
        # conexión (algunos servidores/tests cancelan la tarea del handler
        # al detectar el disconnect), el guardado final del room no debe
        # abortarse a mitad de camino — tiene que terminar sí o sí antes de
        # destruir el documento en memoria.
        await asyncio.shield(yjs_rooms.gestor_salas.desconectar(proyecto_id))
