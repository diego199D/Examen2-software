"""Segundo parcial — WebSocket JSON de la sala de un proyecto (chat grupal,
presencia y Desarrollador Senior). Protocolo de eventos: ver el encabezado
de `app/services/sala.py` y docs/documentacion-tecnica.md.

Mismo control de acceso que el WebSocket de Yjs (CU10): JWT por query param
y `obtener_proyecto_con_acceso` (dueño, colaborador activo o integrante del
mismo grupo) ANTES de aceptar la conexión."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers.ws_diagramas import (
    CIERRE_PROYECTO_NO_ENCONTRADO,
    CIERRE_SIN_ACCESO,
    CIERRE_SIN_TOKEN,
    _usuario_desde_token,
)
from app.services import sala as sala_mod
from app.services import yjs_rooms
from app.services.acceso import obtener_proyecto_con_acceso
from app.services.sala import Conexion, evento

router = APIRouter(tags=["sala-tiempo-real"])


@router.websocket("/ws/proyectos/{proyecto_id}/sala")
async def ws_sala(
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
        await websocket.close(code=CIERRE_PROYECTO_NO_ENCONTRADO if exc.status_code == 404 else CIERRE_SIN_ACCESO)
        return

    datos_usuario = {"id": usuario.id, "nombre": usuario.nombre_completo}
    grupo = usuario.nombre_grupo
    db.close()  # la conexión puede durar horas: no retener la sesión del request

    await websocket.accept()
    conexion = Conexion(websocket=websocket, usuario_id=usuario.id, nombre=usuario.nombre_completo)
    sala, nuevo_usuario = await sala_mod.gestor_chat.conectar(proyecto_id, conexion)

    try:
        await _enviar_estado_inicial(sala, conexion, datos_usuario, grupo)
        if nuevo_usuario:
            await sala.broadcast(evento("USER_JOINED", {"usuario": datos_usuario}), excepto=conexion)
        await sala.broadcast(evento("PRESENCE_LIST", {"usuarios": sala.presentes()}))

        while True:
            mensaje = await websocket.receive_json()
            if not isinstance(mensaje, dict):
                continue
            tipo = mensaje.get("type")
            payload = mensaje.get("payload") or {}
            if tipo == "CHAT_MESSAGE":
                await sala.recibir_mensaje(
                    conexion, str(payload.get("texto") or ""), bool(payload.get("preguntar_senior"))
                )
            elif tipo == "AI_ACTION_DECISION":
                try:
                    mensaje_id = int(payload.get("mensaje_id"))
                except (TypeError, ValueError):
                    await conexion.enviar(evento("ERROR", {"mensaje": "mensaje_id inválido"}))
                    continue
                await sala.decidir(mensaje_id, bool(payload.get("aprobar")), conexion.nombre)
            elif tipo == "SET_AI_MODE":
                await sala.cambiar_modo(str(payload.get("modo") or ""), conexion.nombre)
            elif tipo == "SYNC_REQUEST":
                await _enviar_estado_inicial(sala, conexion, datos_usuario, grupo)
            elif tipo == "PING":
                await conexion.enviar(evento("PONG"))
            else:
                await conexion.enviar(evento("ERROR", {"mensaje": f"Evento desconocido: {tipo}"}))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        sala_restante, se_fue = await sala_mod.gestor_chat.desconectar(proyecto_id, conexion)
        if sala_restante is not None and sala_restante.conexiones:
            if se_fue:
                await sala_restante.broadcast(evento("USER_LEFT", {"usuario": datos_usuario}))
            await sala_restante.broadcast(evento("PRESENCE_LIST", {"usuarios": sala_restante.presentes()}))


async def _enviar_estado_inicial(sala, conexion: Conexion, datos_usuario: dict, grupo: str | None) -> None:
    mensajes, modo = await asyncio.to_thread(sala.historial)
    diagrama, version = await yjs_rooms.leer_diagrama(sala.proyecto_id)
    await conexion.enviar(evento("WELCOME", {"usuario": datos_usuario, "grupo": grupo, "modo_ia": modo}))
    await conexion.enviar(evento("CHAT_HISTORY", {"mensajes": mensajes}))
    await conexion.enviar(evento("DIAGRAM_SNAPSHOT", {"diagrama": diagrama.model_dump(mode="json"), "version": version}))
    await conexion.enviar(evento("PRESENCE_LIST", {"usuarios": sala.presentes()}))
