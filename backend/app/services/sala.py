"""
Segundo parcial (RF-RT-01..05, RF-IA-01..12) — sala en tiempo real de un
proyecto: presencia, chat grupal persistido y el Desarrollador Senior.

Convive con el WebSocket de Yjs de CU10 (`yjs_rooms.py`), que sigue siendo
el canal del diagrama: cada edición viaja como operación atómica de CRDT y
el servidor la persiste (ver docs/decisiones.md, sección 3). Esta sala usa
un protocolo JSON de eventos `{"type": ..., "payload": {...}}`:

Cliente → servidor
- `CHAT_MESSAGE {texto, preguntar_senior}`
- `AI_ACTION_DECISION {mensaje_id, aprobar}`  (con_confirmacion)
- `SET_AI_MODE {modo}`
- `SYNC_REQUEST {}`  → reenvía historial + snapshot
- `PING {}`          → `PONG`

Servidor → cliente
- `WELCOME {usuario, grupo, modo_ia}`
- `PRESENCE_LIST {usuarios}` · `USER_JOINED {usuario}` · `USER_LEFT {usuario}`
- `CHAT_HISTORY {mensajes}` · `CHAT_MESSAGE {mensaje}` · `CHAT_MESSAGE_UPDATED {mensaje}`
- `AI_TYPING {activo, para, en_cola}`
- `AI_DIAGRAM_ACTION_PROPOSED {mensaje_id, resumen, acciones}`
- `AI_DIAGRAM_ACTION_EXECUTED {mensaje_id, resumen, version, diagrama, por}`
- `AI_DIAGRAM_ACTION_REJECTED {mensaje_id, por}`
- `AI_MODE_CHANGED {modo, por}`
- `DIAGRAM_SNAPSHOT {diagrama, version}`
- `ERROR {mensaje}` · `PONG {}`

Cola por sala (RF-IA-07): las preguntas al Senior se encolan y un único
worker por sala las procesa en orden, cada una con su propio contexto.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import WebSocket
from sqlalchemy import func, or_, select

from app.models.mensaje_chat import MensajeChat, TipoMensaje
from app.models.proyecto import Proyecto
from app.models.usuario import Usuario
from app.services import senior, yjs_rooms
from app.services.ai.gemini_client import IANoDisponibleError, IARespuestaInvalidaError
from app.services.mutaciones import MutacionInvalidaError, aplicar_mutaciones

logger = logging.getLogger(__name__)

LIMITE_TEXTO = 2000
HISTORIAL_INICIAL = 200


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def evento(tipo: str, payload: dict | None = None) -> dict:
    return {"type": tipo, "payload": payload or {}, "timestamp": _ahora()}


def mensaje_a_dict(m: MensajeChat) -> dict:
    datos = m.datos or {}
    fecha = m.fecha.replace(tzinfo=m.fecha.tzinfo or timezone.utc).isoformat() if m.fecha else _ahora()
    return {
        "id": m.id,
        "autor": {"id": m.id_usuario, "nombre": m.autor_nombre},
        "tipo": m.tipo.value,
        "texto": m.texto,
        "fecha": fecha,
        "dirigido_a": datos.get("dirigido_a"),
        "propuesta": datos.get("propuesta"),
    }


@dataclass(eq=False)
class Conexion:
    websocket: WebSocket
    usuario_id: int
    nombre: str
    id: int = field(default_factory=itertools.count().__next__)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def enviar(self, ev: dict) -> None:
        async with self._lock:
            await self.websocket.send_json(ev)


@dataclass
class PeticionSenior:
    mensaje_id: int
    usuario_id: int
    nombre: str
    texto: str


class Sala:
    def __init__(self, proyecto_id: int) -> None:
        self.proyecto_id = proyecto_id
        self.conexiones: list[Conexion] = []
        self.cola: asyncio.Queue[PeticionSenior] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self.procesando = False
        self._lock_diagrama = asyncio.Lock()

    # -- presencia ----------------------------------------------------------------
    def presentes(self) -> list[dict]:
        vistos: dict[int, dict] = {}
        for c in self.conexiones:
            vistos.setdefault(c.usuario_id, {"id": c.usuario_id, "nombre": c.nombre})
        return list(vistos.values())

    async def broadcast(self, ev: dict, excepto: Conexion | None = None) -> None:
        for c in list(self.conexiones):
            if c is excepto:
                continue
            try:
                await c.enviar(ev)
            except Exception:  # conexión caída: la limpia su propio handler
                logger.debug("No se pudo enviar a la conexión %s", c.id)

    def iniciar_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._procesar_cola())

    async def detener(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    # -- Senior -------------------------------------------------------------------
    async def _procesar_cola(self) -> None:
        while True:
            peticion = await self.cola.get()
            self.procesando = True
            try:
                await self.broadcast(
                    evento("AI_TYPING", {"activo": True, "para": peticion.nombre, "en_cola": self.cola.qsize()})
                )
                await self._responder(peticion)
            except Exception:
                logger.exception("Error procesando una pregunta al Senior")
                await self._mensaje_sistema(
                    "El Senior no pudo responder por un error interno. Intenten de nuevo.", tipo_ev="ERROR"
                )
            finally:
                self.procesando = False
                await self.broadcast(evento("AI_TYPING", {"activo": False, "en_cola": self.cola.qsize()}))
                self.cola.task_done()

    async def _responder(self, p: PeticionSenior) -> None:
        diagrama, _ = await yjs_rooms.leer_diagrama(self.proyecto_id)
        contexto = await asyncio.to_thread(self._armar_contexto, p, diagrama)
        try:
            respuesta = await asyncio.to_thread(senior.consultar_senior, contexto)
        except (IANoDisponibleError, IARespuestaInvalidaError) as err:
            await self._guardar_y_emitir(
                autor_nombre=senior.NOMBRE_SENIOR,
                tipo=TipoMensaje.SENIOR_AI,
                texto=senior.asegurar_saludo(f"no pude responderte ahora: {err}", p.nombre),
                datos={"dirigido_a": {"id": p.usuario_id, "nombre": p.nombre}},
            )
            return

        texto = respuesta.texto or (
            "te propongo estos cambios al diagrama." if respuesta.acciones else "no tengo una respuesta para eso."
        )
        datos: dict = {"dirigido_a": {"id": p.usuario_id, "nombre": p.nombre}}
        ejecutar = False
        if respuesta.acciones and contexto.modo != "consultivo":
            try:
                resultado = aplicar_mutaciones(contexto.diagrama, respuesta.acciones)
            except MutacionInvalidaError as err:
                texto += f"\n\n⚠️ No apliqué el cambio porque no es válido: {err}"
            else:
                estado = "aplicada" if contexto.modo == "automatico" else "pendiente"
                if estado == "pendiente":
                    texto += "\n\n(Propuesta pendiente: cualquiera del equipo puede aplicarla o rechazarla.)"
                datos["propuesta"] = {"acciones": respuesta.acciones, "resumen": resultado.resumen, "estado": estado}
                ejecutar = contexto.modo == "automatico"

        mensaje = await self._guardar_y_emitir(
            autor_nombre=senior.NOMBRE_SENIOR,
            tipo=TipoMensaje.SENIOR_AI,
            texto=senior.asegurar_saludo(texto, p.nombre),
            datos=datos,
        )
        if "propuesta" not in datos:
            return
        if ejecutar:
            await self._ejecutar_propuesta(mensaje["id"], por=senior.NOMBRE_SENIOR)
        else:
            await self.broadcast(
                evento(
                    "AI_DIAGRAM_ACTION_PROPOSED",
                    {"mensaje_id": mensaje["id"], "resumen": datos["propuesta"]["resumen"], "acciones": respuesta.acciones},
                )
            )

    def _armar_contexto(self, p: PeticionSenior, diagrama) -> senior.ContextoSenior:
        db = yjs_rooms._nueva_sesion()
        try:
            proyecto = db.get(Proyecto, self.proyecto_id)
            autor = db.get(Usuario, p.usuario_id)
            grupo = (autor.nombre_grupo if autor else None) or proyecto.administrador.nombre_grupo or "(sin grupo)"
            self._resumir_si_hace_falta(db, proyecto)
            # Todo lo anterior a la pregunta + las respuestas del Senior que
            # llegaron mientras esperaba en la cola; nunca preguntas humanas
            # posteriores (son de otra petición: no mezclar contextos).
            filtro = [
                MensajeChat.id_proyecto == self.proyecto_id,
                MensajeChat.id != p.mensaje_id,
                or_(MensajeChat.id < p.mensaje_id, MensajeChat.tipo == TipoMensaje.SENIOR_AI),
            ]
            if proyecto.resumen_hasta_id:
                filtro.append(MensajeChat.id > proyecto.resumen_hasta_id)
            recientes = list(
                db.scalars(select(MensajeChat).where(*filtro).order_by(MensajeChat.id.desc()).limit(senior.HISTORIAL_N))
            )[::-1]
            historial = [
                senior.MensajeHistorial(autor=m.autor_nombre, es_ia=m.tipo == TipoMensaje.SENIOR_AI, texto=_texto_historial(m))
                for m in recientes
                if m.tipo != TipoMensaje.SISTEMA or (m.datos or {}).get("relevante")
            ]
            modo = proyecto.modo_ia if proyecto.modo_ia in senior.MODOS else "automatico"
            resumen = proyecto.resumen_chat
        finally:
            db.close()
        return senior.ContextoSenior(
            grupo=grupo,
            modo=modo,
            diagrama=diagrama,
            historial=historial,
            resumen=resumen,
            autor_id=p.usuario_id,
            autor_nombre=p.nombre,
            pregunta=p.texto,
        )

    def _resumir_si_hace_falta(self, db, proyecto: Proyecto) -> None:
        desde = proyecto.resumen_hasta_id or 0
        pendientes = db.scalar(
            select(func.count()).select_from(MensajeChat).where(
                MensajeChat.id_proyecto == self.proyecto_id, MensajeChat.id > desde
            )
        )
        if not pendientes or pendientes <= senior.UMBRAL_RESUMEN:
            return
        viejos = list(
            db.scalars(
                select(MensajeChat)
                .where(MensajeChat.id_proyecto == self.proyecto_id, MensajeChat.id > desde)
                .order_by(MensajeChat.id)
                .limit(pendientes - senior.HISTORIAL_N)
            )
        )
        if not viejos:
            return
        try:
            nuevo = senior.resumir(
                proyecto.resumen_chat,
                [senior.MensajeHistorial(m.autor_nombre, m.tipo == TipoMensaje.SENIOR_AI, _texto_historial(m)) for m in viejos],
            )
        except (IANoDisponibleError, IARespuestaInvalidaError):
            return  # se reintenta en la próxima pregunta; el contexto sigue con la ventana
        if nuevo:
            proyecto.resumen_chat = nuevo
            proyecto.resumen_hasta_id = viejos[-1].id
            db.commit()

    # -- propuestas -----------------------------------------------------------------
    async def decidir(self, mensaje_id: int, aprobar: bool, usuario_nombre: str) -> None:
        if not aprobar:
            ok = await asyncio.to_thread(self._marcar_propuesta, mensaje_id, "pendiente", "rechazada", usuario_nombre)
            if ok:
                await self.broadcast(evento("AI_DIAGRAM_ACTION_REJECTED", {"mensaje_id": mensaje_id, "por": usuario_nombre}))
                await self._emitir_actualizado(mensaje_id)
            return
        await self._ejecutar_propuesta(mensaje_id, por=usuario_nombre)

    async def _ejecutar_propuesta(self, mensaje_id: int, por: str) -> None:
        async with self._lock_diagrama:
            propuesta = await asyncio.to_thread(self._leer_propuesta, mensaje_id)
            if propuesta is None:
                return
            if por != senior.NOMBRE_SENIOR and propuesta.get("estado") != "pendiente":
                return  # ya decidida por otro integrante
            diagrama, _ = await yjs_rooms.leer_diagrama(self.proyecto_id)
            try:
                # Se re-valida contra el diagrama ACTUAL (pudo cambiar desde la propuesta).
                resultado = aplicar_mutaciones(diagrama, propuesta["acciones"])
            except MutacionInvalidaError as err:
                await asyncio.to_thread(self._marcar_propuesta, mensaje_id, None, "fallida", por)
                await self._emitir_actualizado(mensaje_id)
                await self._mensaje_sistema(f"La propuesta ya no se puede aplicar: {err}", tipo_ev="ERROR")
                return
            version = await yjs_rooms.escribir_diagrama(self.proyecto_id, resultado.diagrama)
            await asyncio.to_thread(self._marcar_propuesta, mensaje_id, None, "aplicada", por)
        await self.broadcast(
            evento(
                "AI_DIAGRAM_ACTION_EXECUTED",
                {
                    "mensaje_id": mensaje_id,
                    "resumen": resultado.resumen,
                    "version": version,
                    "diagrama": resultado.diagrama.model_dump(mode="json"),
                    "por": por,
                },
            )
        )
        await self._emitir_actualizado(mensaje_id)

    def _leer_propuesta(self, mensaje_id: int) -> dict | None:
        db = yjs_rooms._nueva_sesion()
        try:
            m = db.get(MensajeChat, mensaje_id)
            if m is None or m.id_proyecto != self.proyecto_id:
                return None
            return (m.datos or {}).get("propuesta")
        finally:
            db.close()

    def _marcar_propuesta(self, mensaje_id: int, si_estado: str | None, nuevo: str, por: str) -> bool:
        db = yjs_rooms._nueva_sesion()
        try:
            m = db.get(MensajeChat, mensaje_id)
            if m is None or m.id_proyecto != self.proyecto_id or not (m.datos or {}).get("propuesta"):
                return False
            datos = dict(m.datos)
            propuesta = dict(datos["propuesta"])
            if si_estado is not None and propuesta.get("estado") != si_estado:
                return False
            propuesta["estado"] = nuevo
            propuesta["decidida_por"] = por
            datos["propuesta"] = propuesta
            m.datos = datos
            db.commit()
            return True
        finally:
            db.close()

    async def _emitir_actualizado(self, mensaje_id: int) -> None:
        def leer():
            db = yjs_rooms._nueva_sesion()
            try:
                m = db.get(MensajeChat, mensaje_id)
                return mensaje_a_dict(m) if m else None
            finally:
                db.close()

        datos = await asyncio.to_thread(leer)
        if datos:
            await self.broadcast(evento("CHAT_MESSAGE_UPDATED", {"mensaje": datos}))

    # -- persistencia de mensajes -------------------------------------------------
    async def _guardar_y_emitir(self, **campos) -> dict:
        def guardar():
            db = yjs_rooms._nueva_sesion()
            try:
                m = MensajeChat(id_proyecto=self.proyecto_id, **campos)
                db.add(m)
                db.commit()
                db.refresh(m)
                return mensaje_a_dict(m)
            finally:
                db.close()

        datos = await asyncio.to_thread(guardar)
        await self.broadcast(evento("CHAT_MESSAGE", {"mensaje": datos}))
        return datos

    async def _mensaje_sistema(self, texto: str, tipo_ev: str | None = None) -> None:
        if tipo_ev == "ERROR":
            await self.broadcast(evento("ERROR", {"mensaje": texto}))
        await self._guardar_y_emitir(autor_nombre="Sistema", tipo=TipoMensaje.SISTEMA, texto=texto, datos=None)

    async def recibir_mensaje(self, conexion: Conexion, texto: str, preguntar_senior: bool) -> None:
        texto = (texto or "").strip()
        if not texto:
            return
        if len(texto) > LIMITE_TEXTO:
            await conexion.enviar(evento("ERROR", {"mensaje": f"El mensaje supera {LIMITE_TEXTO} caracteres."}))
            return
        datos = await self._guardar_y_emitir(
            id_usuario=conexion.usuario_id,
            autor_nombre=conexion.nombre,
            tipo=TipoMensaje.HUMANO,
            texto=texto,
            datos={"preguntar_senior": True} if preguntar_senior else None,
        )
        if preguntar_senior or senior.menciona_al_senior(texto):
            await self.cola.put(PeticionSenior(datos["id"], conexion.usuario_id, conexion.nombre, texto))
            if self.cola.qsize() > 1:
                await self.broadcast(evento("AI_TYPING", {"activo": True, "en_cola": self.cola.qsize()}))

    async def cambiar_modo(self, modo: str, por: str) -> None:
        if modo not in senior.MODOS:
            return

        def guardar():
            db = yjs_rooms._nueva_sesion()
            try:
                proyecto = db.get(Proyecto, self.proyecto_id)
                proyecto.modo_ia = modo
                db.commit()
            finally:
                db.close()

        await asyncio.to_thread(guardar)
        await self.broadcast(evento("AI_MODE_CHANGED", {"modo": modo, "por": por}))

    def historial(self) -> tuple[list[dict], str]:
        db = yjs_rooms._nueva_sesion()
        try:
            proyecto = db.get(Proyecto, self.proyecto_id)
            mensajes = list(
                db.scalars(
                    select(MensajeChat)
                    .where(MensajeChat.id_proyecto == self.proyecto_id)
                    .order_by(MensajeChat.id.desc())
                    .limit(HISTORIAL_INICIAL)
                )
            )[::-1]
            return [mensaje_a_dict(m) for m in mensajes], proyecto.modo_ia
        finally:
            db.close()


def _texto_historial(m: MensajeChat) -> str:
    propuesta = (m.datos or {}).get("propuesta")
    if not propuesta:
        return m.texto
    estado = propuesta.get("estado")
    return m.texto + f"\n(Cambios {estado}: " + " ".join(propuesta.get("resumen") or []) + ")"


class GestorChat:
    def __init__(self) -> None:
        self.salas: dict[int, Sala] = {}
        self._lock = asyncio.Lock()

    async def conectar(self, proyecto_id: int, conexion: Conexion) -> tuple[Sala, bool]:
        async with self._lock:
            sala = self.salas.get(proyecto_id)
            if sala is None:
                sala = Sala(proyecto_id)
                self.salas[proyecto_id] = sala
            nuevo_usuario = all(c.usuario_id != conexion.usuario_id for c in sala.conexiones)
            sala.conexiones.append(conexion)
            sala.iniciar_worker()
            return sala, nuevo_usuario

    async def desconectar(self, proyecto_id: int, conexion: Conexion) -> tuple[Sala | None, bool]:
        async with self._lock:
            sala = self.salas.get(proyecto_id)
            if sala is None:
                return None, False
            sala.conexiones = [c for c in sala.conexiones if c is not conexion]
            se_fue = all(c.usuario_id != conexion.usuario_id for c in sala.conexiones)
            # Si el Senior está respondiendo, la sala sigue viva hasta terminar
            # (la respuesta se persiste y queda en el historial).
            if not sala.conexiones and sala.cola.empty() and not sala.procesando:
                await sala.detener()
                del self.salas[proyecto_id]
            return sala, se_fue


gestor_chat = GestorChat()
