"""CU10 - Colaboración en tiempo real sobre el diagrama de clases via Yjs.

Cada proyecto con al menos un cliente conectado tiene un "room": un
`pycrdt.Doc` en memoria, compartido entre todos los clientes WebSocket
conectados a ese proyecto y sincronizado automáticamente por
`pycrdt.websocket.YRoom` (protocolo de sync + awareness de Yjs — ver
app/routers/ws_diagramas.py para el endpoint que llama a `YRoom.serve()`).

Estructura del documento Yjs (Y.Map anidados, no blobs JSON opacos —
así cada campo es una entrada de CRDT independiente y se puede fusionar
sin pisar el resto de la clase/relación):

    doc["clases"]      -> Map[clase_id -> Map{
                               id, nombre, estereotipo, es_abstracta,
                               pos_x, pos_y,
                               atributos: Map[attr_id -> Map{...}],
                               metodos:   Map[met_id  -> Map{...}],
                           }]
    doc["relaciones"]  -> Map[relacion_id -> Map{
                               id, id_clase_origen, id_clase_destino, tipo,
                               etiqueta, multiplicidad_origen,
                               multiplicidad_destino, handle_origen,
                               handle_destino, forma, desvio_x, desvio_y,
                           }]

Cada cambio al documento se vuelca a las tablas normalizadas con debounce,
reutilizando `app.services.diagrama.guardar_diagrama` (la misma lógica de
reemplazo completo que usa el autoguardado HTTP de CU09) — no se
reimplementa la persistencia."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from pycrdt import Doc, Map
from pycrdt.websocket import YRoom
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.schemas.diagrama import ClaseIO, DiagramaIO, RelacionIO
from app.services.diagrama import cargar_diagrama, guardar_diagrama

logger = logging.getLogger(__name__)

# Tiempo de inactividad antes de persistir a la BD tras el último cambio.
DEBOUNCE_SEGUNDOS = 4.0

# Fábrica de sesiones usada por los rooms para hidratar/guardar el diagrama.
# Es un módulo-nivel reemplazable (no una constante) para que los tests
# puedan apuntarla a la BD SQLite en memoria de la fixture `db_session` en
# vez de a la BD real de app.db.session.SessionLocal — ver
# tests/test_ws_diagramas.py.
_session_factory: Callable[[], Session] = SessionLocal


def set_session_factory(factory: Callable[[], Session]) -> None:
    global _session_factory
    _session_factory = factory


def _nueva_sesion() -> Session:
    return _session_factory()


def _clase_a_map(clase: ClaseIO) -> Map:
    datos = clase.model_dump(mode="json")
    campos_planos = {k: v for k, v in datos.items() if k not in ("atributos", "metodos")}
    return Map(
        {
            **campos_planos,
            "atributos": Map({a["id"]: Map(a) for a in datos["atributos"]}),
            "metodos": Map({m["id"]: Map(m) for m in datos["metodos"]}),
        }
    )


def _relacion_a_map(relacion: RelacionIO) -> Map:
    return Map(relacion.model_dump(mode="json"))


def _map_a_clase(datos: dict) -> ClaseIO:
    datos = dict(datos)
    datos["atributos"] = list((datos.get("atributos") or {}).values())
    datos["metodos"] = list((datos.get("metodos") or {}).values())
    return ClaseIO(**datos)


class DiagramaRoom:
    """Un room de colaboración para un proyecto: documento Yjs en memoria +
    guardado con debounce hacia la BD normalizada."""

    def __init__(self, proyecto_id: int, estado_inicial: DiagramaIO) -> None:
        self.proyecto_id = proyecto_id
        self.clientes = 0
        self._guardado_pendiente: asyncio.TimerHandle | None = None
        self._guardando = asyncio.Lock()
        self._tarea_room: asyncio.Task | None = None

        self.ydoc = Doc()
        self._clases = self.ydoc.get("clases", type=Map)
        self._relaciones = self.ydoc.get("relaciones", type=Map)
        with self.ydoc.transaction():
            for c in estado_inicial.clases:
                self._clases[c.id] = _clase_a_map(c)
            for r in estado_inicial.relaciones:
                self._relaciones[r.id] = _relacion_a_map(r)

        self.yroom = YRoom(ydoc=self.ydoc)
        # Se registra DESPUÉS de sembrar el estado inicial: no queremos
        # disparar un guardado (redundante, es lo que ya hay en la BD) apenas
        # se crea el room.
        self.ydoc.observe(self._on_change)

    async def iniciar(self) -> None:
        self._tarea_room = asyncio.create_task(self.yroom.start())
        await self.yroom.started.wait()

    async def detener(self) -> None:
        await self.yroom.stop()
        if self._tarea_room is not None:
            await self._tarea_room

    def _on_change(self, event) -> None:
        self._programar_guardado()

    def _programar_guardado(self) -> None:
        loop = asyncio.get_running_loop()
        if self._guardado_pendiente is not None:
            self._guardado_pendiente.cancel()
        self._guardado_pendiente = loop.call_later(
            DEBOUNCE_SEGUNDOS, lambda: loop.create_task(self._guardar())
        )

    def _diagrama_actual(self) -> DiagramaIO:
        clases_raw = self._clases.to_py() or {}
        relaciones_raw = self._relaciones.to_py() or {}
        return DiagramaIO(
            clases=[_map_a_clase(c) for c in clases_raw.values()],
            relaciones=[RelacionIO(**r) for r in relaciones_raw.values()],
        )

    async def guardar_ahora(self) -> None:
        """Cancela el debounce pendiente (si hay) y guarda de inmediato.
        Se usa al desconectarse el último cliente del room."""
        if self._guardado_pendiente is not None:
            self._guardado_pendiente.cancel()
            self._guardado_pendiente = None
        await self._guardar()

    async def _guardar(self) -> None:
        async with self._guardando:
            datos = self._diagrama_actual()
            await asyncio.to_thread(self._guardar_sync, datos)

    def _guardar_sync(self, datos: DiagramaIO) -> None:
        db = _nueva_sesion()
        try:
            guardar_diagrama(self.proyecto_id, datos, db)
        except Exception:
            logger.exception(
                "No se pudo persistir el diagrama del proyecto %s (room colaborativo)",
                self.proyecto_id,
            )
        finally:
            db.close()


class GestorSalas:
    """Registro de rooms activos, uno por proyecto (proyecto_id -> room).
    Crea el room (hidratado desde la BD) en la primera conexión y lo
    destruye (con guardado final) cuando se queda sin clientes."""

    def __init__(self) -> None:
        self._salas: dict[int, DiagramaRoom] = {}
        self._lock = asyncio.Lock()

    async def conectar(self, proyecto_id: int) -> DiagramaRoom:
        async with self._lock:
            sala = self._salas.get(proyecto_id)
            if sala is None:
                estado_inicial = await asyncio.to_thread(_cargar_estado_inicial, proyecto_id)
                sala = DiagramaRoom(proyecto_id, estado_inicial)
                await sala.iniciar()
                self._salas[proyecto_id] = sala
            sala.clientes += 1
            return sala

    async def desconectar(self, proyecto_id: int) -> None:
        async with self._lock:
            sala = self._salas.get(proyecto_id)
            if sala is None:
                return
            sala.clientes -= 1
            if sala.clientes > 0:
                return
            # Se quita del registro ya bajo el lock: una conexión nueva que
            # llegue justo ahora no reutiliza este room (que ya se está por
            # apagar), crea uno nuevo hidratado desde lo que el guardado
            # final de abajo está por dejar en la BD.
            del self._salas[proyecto_id]

        await sala.guardar_ahora()
        await sala.detener()

    def sala_activa(self, proyecto_id: int) -> DiagramaRoom | None:
        return self._salas.get(proyecto_id)


def _cargar_estado_inicial(proyecto_id: int) -> DiagramaIO:
    db = _nueva_sesion()
    try:
        return cargar_diagrama(proyecto_id, db)
    finally:
        db.close()


gestor_salas = GestorSalas()
