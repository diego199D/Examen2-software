"""CU10 - Colaboración en tiempo real (Yjs). Simula clientes reales del
protocolo de sincronización de Yjs con pycrdt (sin depender del frontend,
que todavía no está cableado) para probar, contra el WebSocket real del
backend:

- que dos conexiones al mismo proyecto se sincronizan en tiempo real,
- que un cliente que se conecta después recibe el estado actual del room
  (no uno viejo leído de la BD),
- que el guardado con debounce efectivamente persiste a la BD,
- y que el control de acceso (dueño/colaborador activo/nada) se aplica
  ANTES de aceptar la conexión, con códigos de cierre distintos.
"""

import time

import pytest
from fastapi.testclient import TestClient
from pycrdt import Doc, Map, create_sync_message, create_update_message, handle_sync_message
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.core.security import crear_access_token, hashear_password
from app.db.session import Base, get_db
from app.main import app
from app.models.clase_uml import ClaseUml
from app.models.proyecto import Proyecto
from app.models.proyecto_colaborador import ProyectoColaborador
from app.models.usuario import RolUsuario, Usuario
from app.services import yjs_rooms
from app.services.yjs_rooms import GestorSalas


# --- infraestructura de test propia (no la de conftest.py): el room
# colaborativo guarda en un hilo aparte con SU PROPIA fábrica de sesiones
# (app.services.yjs_rooms.set_session_factory), así que necesitamos que
# tanto el get_db de los endpoints HTTP/WS como esa fábrica apunten al
# mismo engine SQLite en memoria. ---


@pytest.fixture()
def ws_session_local():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _activar_fk(conexion_dbapi, _):
        conexion_dbapi.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield SessionLocal
    Base.metadata.drop_all(engine)


@pytest.fixture()
def ws_client(ws_session_local):
    def _get_db_override():
        db = ws_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db_override
    yjs_rooms.set_session_factory(ws_session_local)
    # Room registry nuevo (con sus propios asyncio.Lock) para no reutilizar
    # locks creados en el event loop de un TestClient/test anterior.
    yjs_rooms.gestor_salas = GestorSalas()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def _crear_usuario(SessionLocal, nombre="Ana") -> Usuario:
    db = SessionLocal()
    try:
        usuario = Usuario(
            nombre_completo=nombre,
            email=f"{nombre.lower()}@test.com",
            password_hash=hashear_password("clave12345"),
            rol=RolUsuario.ADMINISTRADOR,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario
    finally:
        db.close()


def _crear_proyecto(SessionLocal, admin: Usuario, nombre="Proyecto colaborativo") -> Proyecto:
    db = SessionLocal()
    try:
        proyecto = Proyecto(nombre=nombre, id_administrador=admin.id)
        db.add(proyecto)
        db.commit()
        db.refresh(proyecto)
        return proyecto
    finally:
        db.close()


def _agregar_colaborador(SessionLocal, proyecto: Proyecto, usuario: Usuario) -> None:
    db = SessionLocal()
    try:
        db.add(ProyectoColaborador(id_proyecto=proyecto.id, id_usuario=usuario.id, activo=True))
        db.commit()
    finally:
        db.close()


def _token(usuario: Usuario) -> str:
    return crear_access_token(subject=usuario.id)


def _url(proyecto_id: int, token: str) -> str:
    return f"/ws/proyectos/{proyecto_id}/diagrama?token={token}"


# --- helpers del protocolo de sync de Yjs, para simular un cliente real ---


def _handshake_inicial(ws, doc: Doc) -> None:
    """Reproduce lo que hace un provider real de Yjs al conectar:
    1) recibe el STEP1 (vector de estado) que el servidor manda apenas
       acepta la conexión, y responde con lo que el servidor le pide;
    2) manda su propio STEP1 (vector vacío) para pedirle al servidor todo
       su contenido, y aplica el STEP2 que responde."""
    msg_servidor = ws.receive_bytes()
    reply = handle_sync_message(msg_servidor[1:], doc)
    if reply is not None:
        ws.send_bytes(reply)

    ws.send_bytes(create_sync_message(doc))
    msg_contenido = ws.receive_bytes()
    handle_sync_message(msg_contenido[1:], doc)


def _mandar_cambio(ws, doc: Doc, mutar) -> None:
    estado_previo = doc.get_state()
    with doc.transaction():
        mutar(doc)
    update = doc.get_update(estado_previo)
    ws.send_bytes(create_update_message(update))


def _recibir_cambio(ws, doc: Doc) -> None:
    msg = ws.receive_bytes()
    handle_sync_message(msg[1:], doc)


def _agregar_clase(doc: Doc, clase_id: str, nombre: str) -> None:
    clases = doc.get("clases", type=Map)
    clases[clase_id] = Map(
        {
            "id": clase_id,
            "nombre": nombre,
            "estereotipo": None,
            "es_abstracta": False,
            "pos_x": 0.0,
            "pos_y": 0.0,
            "atributos": Map({}),
            "metodos": Map({}),
        }
    )


def _nombres_clases(doc: Doc) -> set[str]:
    clases = doc.get("clases", type=Map).to_py() or {}
    return {c["nombre"] for c in clases.values()}


# --- tests ---


def test_dos_clientes_sincronizan_en_tiempo_real(ws_client, ws_session_local):
    admin = _crear_usuario(ws_session_local, "Ana")
    colaborador = _crear_usuario(ws_session_local, "Beto")
    proyecto = _crear_proyecto(ws_session_local, admin)
    _agregar_colaborador(ws_session_local, proyecto, colaborador)

    with ws_client.websocket_connect(_url(proyecto.id, _token(admin))) as ws_a:
        doc_a = Doc()
        _handshake_inicial(ws_a, doc_a)
        assert _nombres_clases(doc_a) == set()  # diagrama nuevo, sin clases

        with ws_client.websocket_connect(_url(proyecto.id, _token(colaborador))) as ws_b:
            doc_b = Doc()
            _handshake_inicial(ws_b, doc_b)

            # A crea una clase y la manda al servidor.
            _mandar_cambio(ws_a, doc_a, lambda d: _agregar_clase(d, "clase-1", "Cliente"))
            # El servidor reenvía todo update a TODOS los clientes del room,
            # incluido el que lo mandó (así es como Yjs mantiene la
            # conexión viva) -- hay que drenar ese eco antes de seguir.
            _recibir_cambio(ws_a, doc_a)

            # El servidor debe reenviárselo a B (el otro cliente conectado
            # al mismo proyecto) en tiempo real.
            _recibir_cambio(ws_b, doc_b)
            assert _nombres_clases(doc_b) == {"Cliente"}

            # Y a la inversa: B edita y A ve el cambio.
            _mandar_cambio(ws_b, doc_b, lambda d: _agregar_clase(d, "clase-2", "Pedido"))
            _recibir_cambio(ws_b, doc_b)  # eco propio
            _recibir_cambio(ws_a, doc_a)
            assert _nombres_clases(doc_a) == {"Cliente", "Pedido"}

        # B se desconectó; un tercer cliente (reconexión) debe ver el
        # estado actual del room -- incluye lo que B mandó -- no una copia
        # vieja recién leída de la BD.
        with ws_client.websocket_connect(_url(proyecto.id, _token(admin))) as ws_c:
            doc_c = Doc()
            _handshake_inicial(ws_c, doc_c)
            assert _nombres_clases(doc_c) == {"Cliente", "Pedido"}


def test_persistencia_final_al_quedar_sin_clientes(ws_client, ws_session_local):
    admin = _crear_usuario(ws_session_local, "Carla")
    proyecto = _crear_proyecto(ws_session_local, admin)

    with ws_client.websocket_connect(_url(proyecto.id, _token(admin))) as ws:
        doc = Doc()
        _handshake_inicial(ws, doc)
        _mandar_cambio(ws, doc, lambda d: _agregar_clase(d, "clase-1", "Factura"))
        # Se cierra sin esperar el debounce: al quedar el room sin
        # clientes, GestorSalas.desconectar fuerza un guardado inmediato.
        # (El guardado corre protegido con asyncio.shield porque el
        # TestClient cancela la tarea del handler al salir de este `with`
        # -- por eso el chequeo de abajo es con reintentos: el guardado
        # sigue corriendo en background un instante más.)

    def _clases_guardadas():
        db = ws_session_local()
        try:
            return list(db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == proyecto.id)))
        finally:
            db.close()

    for _ in range(20):
        if _clases_guardadas():
            break
        time.sleep(0.05)

    assert [c.nombre for c in _clases_guardadas()] == ["Factura"]


def test_guardado_con_debounce_mientras_el_cliente_sigue_conectado(
    ws_client, ws_session_local, monkeypatch
):
    monkeypatch.setattr(yjs_rooms, "DEBOUNCE_SEGUNDOS", 0.3)

    admin = _crear_usuario(ws_session_local, "Diego")
    proyecto = _crear_proyecto(ws_session_local, admin)

    with ws_client.websocket_connect(_url(proyecto.id, _token(admin))) as ws:
        doc = Doc()
        _handshake_inicial(ws, doc)
        _mandar_cambio(ws, doc, lambda d: _agregar_clase(d, "clase-1", "Producto"))

        # Sin desconectar: hay que esperar el debounce, no el guardado
        # final por desconexión.
        time.sleep(0.6)

        db = ws_session_local()
        try:
            clases = list(
                db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == proyecto.id))
            )
            assert [c.nombre for c in clases] == ["Producto"]
        finally:
            db.close()


def test_diagrama_existente_en_bd_hidrata_el_room_al_conectar(ws_client, ws_session_local):
    admin = _crear_usuario(ws_session_local, "Elena")
    proyecto = _crear_proyecto(ws_session_local, admin)
    db = ws_session_local()
    try:
        db.add(
            ClaseUml(
                id="clase-existente",
                id_proyecto=proyecto.id,
                nombre="YaExistia",
                pos_x=0,
                pos_y=0,
            )
        )
        db.commit()
    finally:
        db.close()

    with ws_client.websocket_connect(_url(proyecto.id, _token(admin))) as ws:
        doc = Doc()
        _handshake_inicial(ws, doc)
        assert _nombres_clases(doc) == {"YaExistia"}


def test_rechaza_sin_token(ws_client, ws_session_local):
    admin = _crear_usuario(ws_session_local, "Fer")
    proyecto = _crear_proyecto(ws_session_local, admin)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(f"/ws/proyectos/{proyecto.id}/diagrama"):
            pass
    assert exc_info.value.code == 4401


def test_rechaza_usuario_sin_acceso_al_proyecto(ws_client, ws_session_local):
    admin = _crear_usuario(ws_session_local, "Gaby")
    ajeno = _crear_usuario(ws_session_local, "Hugo")
    proyecto = _crear_proyecto(ws_session_local, admin)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(_url(proyecto.id, _token(ajeno))):
            pass
    assert exc_info.value.code == 4403


def test_rechaza_proyecto_inexistente(ws_client, ws_session_local):
    admin = _crear_usuario(ws_session_local, "Ines")

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(_url(999999, _token(admin))):
            pass
    assert exc_info.value.code == 4404
