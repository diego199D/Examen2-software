"""Segundo parcial — sala en tiempo real (chat grupal, presencia, grupos) y el
Desarrollador Senior, a través del WebSocket real con dos clientes. Gemini
se reemplaza siempre por un falso (`senior.consultar_senior`)."""

import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.core.security import crear_access_token, hashear_password
from app.db.session import Base, get_db
from app.main import app
from app.models.clase_uml import ClaseUml
from app.models.mensaje_chat import MensajeChat
from app.models.proyecto import Proyecto
from app.models.relacion import Relacion
from app.models.usuario import RolUsuario, Usuario
from app.services import sala as sala_mod
from app.services import senior, yjs_rooms
from app.services.grupos import obtener_o_crear_grupo
from app.services.yjs_rooms import GestorSalas


@pytest.fixture()
def SL():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(con, _):
        con.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.drop_all(engine)


@pytest.fixture()
def cliente(SL):
    def _db():
        db = SL()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    yjs_rooms.set_session_factory(SL)
    yjs_rooms.gestor_salas = GestorSalas()
    sala_mod.gestor_chat = sala_mod.GestorChat()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def senior_falso(monkeypatch):
    """Registra cada contexto recibido y devuelve lo que se le indique."""
    estado = {"llamadas": [], "respuesta": senior.RespuestaSenior(texto="respuesta"), "demora": 0}

    def _consultar(ctx):
        estado["llamadas"].append(ctx)
        if estado["demora"]:
            time.sleep(estado["demora"])
        r = estado["respuesta"]
        return r(ctx) if callable(r) else r

    monkeypatch.setattr(senior, "consultar_senior", _consultar)
    return estado


def _usuario(SL, nombre, grupo=None):
    db = SL()
    try:
        u = Usuario(
            nombre_completo=nombre,
            email=f"{nombre.lower()}@test.com",
            password_hash=hashear_password("clave12345"),
            rol=RolUsuario.ADMINISTRADOR,
        )
        if grupo:
            u.grupo = obtener_o_crear_grupo(grupo, db)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def _proyecto(SL, dueño, modo="automatico", clases=(), nombre="Tienda"):
    db = SL()
    try:
        p = Proyecto(nombre=nombre, id_administrador=dueño.id, modo_ia=modo)
        db.add(p)
        # El modo del Senior es del GRUPO (chat único por grupo).
        dueño_db = db.get(Usuario, dueño.id)
        if dueño_db.grupo is not None:
            dueño_db.grupo.modo_ia = modo
        db.commit()
        for i, n in enumerate(clases):
            db.add(ClaseUml(id=f"p{p.id}c{i}", id_proyecto=p.id, nombre=n, pos_x=0, pos_y=0))
        db.commit()
        db.refresh(p)
        return p
    finally:
        db.close()


def _url(p, u):
    return f"/ws/proyectos/{p.id}/sala?token={crear_access_token(subject=u.id)}"


def _hasta(ws, tipo, max_eventos=60, cond=lambda p: True):
    for _ in range(max_eventos):
        ev = ws.receive_json()
        if ev["type"] == tipo and cond(ev["payload"]):
            return ev["payload"]
    raise AssertionError(f"no llegó {tipo}")


def _enviar(ws, texto, preguntar=False):
    ws.send_json({"type": "CHAT_MESSAGE", "payload": {"texto": texto, "preguntar_senior": preguntar}})


@pytest.fixture()
def equipo(SL):
    juan = _usuario(SL, "Juan", grupo="Los Modeladores")
    maria = _usuario(SL, "Maria", grupo="los modeladores")  # mismo grupo (sin distinguir mayúsculas)
    return juan, maria


class TestGrupoYPresencia:
    def test_integrante_del_grupo_entra_y_ajeno_no(self, cliente, SL, equipo):
        juan, maria = equipo
        ajeno = _usuario(SL, "Pedro", grupo="Otro")
        p = _proyecto(SL, juan)
        with cliente.websocket_connect(_url(p, maria)) as ws:
            bienvenida = _hasta(ws, "WELCOME")
            assert bienvenida["grupo"] == "Los Modeladores"
        with pytest.raises(WebSocketDisconnect) as exc:
            with cliente.websocket_connect(_url(p, ajeno)) as ws:
                ws.receive_json()
        assert exc.value.code == 4403

    def test_presencia_y_broadcast_del_chat(self, cliente, SL, equipo, senior_falso):
        juan, maria = equipo
        p = _proyecto(SL, juan)
        with cliente.websocket_connect(_url(p, juan)) as a:
            _hasta(a, "PRESENCE_LIST")
            with cliente.websocket_connect(_url(p, maria)) as b:
                unidos = _hasta(a, "USER_JOINED")
                assert unidos["usuario"]["nombre"] == "Maria"
                lista = _hasta(b, "PRESENCE_LIST", cond=lambda q: len(q["usuarios"]) == 2)
                assert {u["nombre"] for u in lista["usuarios"]} == {"Juan", "Maria"}

                _enviar(a, "hola equipo")
                recibido = _hasta(b, "CHAT_MESSAGE")["mensaje"]
                assert recibido["texto"] == "hola equipo"
                assert recibido["autor"]["nombre"] == "Juan"
                assert recibido["tipo"] == "humano"
            salio = _hasta(a, "USER_LEFT")
            assert salio["usuario"]["nombre"] == "Maria"
        # Un mensaje entre humanos no dispara a la IA.
        assert senior_falso["llamadas"] == []

    def test_chat_persistido_al_reconectar(self, cliente, SL, equipo, senior_falso):
        juan, _ = equipo
        p = _proyecto(SL, juan)
        with cliente.websocket_connect(_url(p, juan)) as a:
            _enviar(a, "primer mensaje")
            _hasta(a, "CHAT_MESSAGE")
        with cliente.websocket_connect(_url(p, juan)) as a:
            historial = _hasta(a, "CHAT_HISTORY")["mensajes"]
            assert [m["texto"] for m in historial] == ["primer mensaje"]
            snapshot = _hasta(a, "DIAGRAM_SNAPSHOT")
            assert "diagrama" in snapshot


class TestSenior:
    def test_escenario_7_1_ambos_ven_la_respuesta_dirigida_a_juan(self, cliente, SL, equipo, senior_falso):
        juan, maria = equipo
        p = _proyecto(SL, juan, clases=["Persona"])
        senior_falso["respuesta"] = senior.RespuestaSenior(
            texto="Un atributo derivado se calcula a partir de otros. Ejemplo: /edad en Persona."
        )
        with cliente.websocket_connect(_url(p, juan)) as a, cliente.websocket_connect(_url(p, maria)) as b:
            _hasta(a, "PRESENCE_LIST")
            _enviar(a, "@senior ¿qué es un atributo derivado?")
            assert _hasta(b, "AI_TYPING", cond=lambda q: q["activo"])["para"] == "Juan"
            for ws in (a, b):
                m = _hasta(ws, "CHAT_MESSAGE", cond=lambda q: q["mensaje"]["tipo"] == "senior_ai")["mensaje"]
                assert m["texto"].startswith("@Juan,")  # RF-IA-04 aunque el modelo no lo hizo
                assert m["dirigido_a"]["nombre"] == "Juan"
        ctx = senior_falso["llamadas"][0]
        assert ctx.autor_nombre == "Juan" and ctx.grupo == "Los Modeladores"
        assert [c.nombre for c in ctx.diagrama.clases] == ["Persona"]

    def test_toggle_preguntar_al_senior(self, cliente, SL, equipo, senior_falso):
        juan, _ = equipo
        p = _proyecto(SL, juan)
        with cliente.websocket_connect(_url(p, juan)) as a:
            _enviar(a, "¿esto está bien?", preguntar=True)
            _hasta(a, "CHAT_MESSAGE", cond=lambda q: q["mensaje"]["tipo"] == "senior_ai")
        assert len(senior_falso["llamadas"]) == 1

    def test_escenario_7_2_automatico_actualiza_el_diagrama(self, cliente, SL, equipo, senior_falso):
        juan, maria = equipo
        p = _proyecto(SL, juan, modo="automatico", clases=["Factura"])
        senior_falso["respuesta"] = senior.RespuestaSenior(
            texto="Maria, agregué DetalleFactura como composición de Factura.",
            acciones=[
                {
                    "action": "ADD_ENTITY",
                    "tempId": "t1",
                    "entityData": {"name": "DetalleFactura", "attributes": [{"name": "cantidad", "type": "int"}]},
                },
                {
                    "action": "ADD_RELATIONSHIP",
                    "relationshipData": {
                        "sourceId": "Factura",
                        "targetId": "t1",
                        "type": "composition",
                        "sourceCardinality": "1",
                        "targetCardinality": "1..*",
                    },
                },
            ],
        )
        with cliente.websocket_connect(_url(p, juan)) as a, cliente.websocket_connect(_url(p, maria)) as b:
            _hasta(b, "PRESENCE_LIST")
            _enviar(b, "Senior, agregale el detalle a la factura")
            ejecutadas = [_hasta(ws, "AI_DIAGRAM_ACTION_EXECUTED") for ws in (a, b)]
            assert ejecutadas[0]["diagrama"] == ejecutadas[1]["diagrama"]
        db = SL()
        nombres = {c.nombre for c in db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == p.id))}
        relaciones = list(db.scalars(select(Relacion).where(Relacion.id_proyecto == p.id)))
        db.close()
        assert nombres == {"Factura", "DetalleFactura"}
        assert len(relaciones) == 1 and relaciones[0].multiplicidad_destino == "1..*"

    def test_con_confirmacion_propone_y_otro_aplica(self, cliente, SL, equipo, senior_falso):
        juan, maria = equipo
        p = _proyecto(SL, juan, modo="con_confirmacion", clases=["Cliente"])
        senior_falso["respuesta"] = senior.RespuestaSenior(
            texto="Juan, te propongo agregar telefono.",
            acciones=[{"action": "ADD_ATTRIBUTE", "entityId": "Cliente", "attributeData": {"name": "telefono", "type": "String"}}],
        )
        with cliente.websocket_connect(_url(p, juan)) as a, cliente.websocket_connect(_url(p, maria)) as b:
            _hasta(a, "PRESENCE_LIST")
            _enviar(a, "@senior agregale teléfono al cliente")
            propuesta = _hasta(b, "AI_DIAGRAM_ACTION_PROPOSED")
            assert propuesta["resumen"] == ["Se agrega el atributo telefono: String a Cliente."]
            db = SL()
            assert not db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == p.id)).one().atributos
            db.close()
            b.send_json({"type": "AI_ACTION_DECISION", "payload": {"mensaje_id": propuesta["mensaje_id"], "aprobar": True}})
            ejecutado = _hasta(a, "AI_DIAGRAM_ACTION_EXECUTED")
            assert ejecutado["por"] == "Maria"
            actualizado = _hasta(a, "CHAT_MESSAGE_UPDATED")["mensaje"]
            assert actualizado["propuesta"]["estado"] == "aplicada"
        db = SL()
        clase = db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == p.id)).one()
        assert [x.nombre for x in clase.atributos] == ["telefono"]
        db.close()

    def test_rechazar_propuesta(self, cliente, SL, equipo, senior_falso):
        juan, _ = equipo
        p = _proyecto(SL, juan, modo="con_confirmacion", clases=["Cliente"])
        senior_falso["respuesta"] = senior.RespuestaSenior(
            texto="Juan, propuesta.", acciones=[{"action": "DELETE_ENTITY", "entityId": "Cliente"}]
        )
        with cliente.websocket_connect(_url(p, juan)) as a:
            _enviar(a, "@senior borrá cliente")
            prop = _hasta(a, "AI_DIAGRAM_ACTION_PROPOSED")
            a.send_json({"type": "AI_ACTION_DECISION", "payload": {"mensaje_id": prop["mensaje_id"], "aprobar": False}})
            _hasta(a, "AI_DIAGRAM_ACTION_REJECTED")
        db = SL()
        assert db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == p.id)).one().nombre == "Cliente"
        db.close()

    def test_consultivo_no_modifica(self, cliente, SL, equipo, senior_falso):
        juan, _ = equipo
        p = _proyecto(SL, juan, modo="consultivo", clases=["Cliente"])
        senior_falso["respuesta"] = senior.RespuestaSenior(
            texto="Juan, habría que borrar Cliente.", acciones=[{"action": "DELETE_ENTITY", "entityId": "Cliente"}]
        )
        with cliente.websocket_connect(_url(p, juan)) as a:
            _enviar(a, "@senior borrá cliente")
            m = _hasta(a, "CHAT_MESSAGE", cond=lambda q: q["mensaje"]["tipo"] == "senior_ai")["mensaje"]
            assert m["propuesta"] is None
        assert senior_falso["llamadas"][0].modo == "consultivo"

    def test_lote_invalido_no_toca_nada_y_se_informa(self, cliente, SL, equipo, senior_falso):
        juan, _ = equipo
        p = _proyecto(SL, juan, modo="automatico", clases=["Cliente"])
        senior_falso["respuesta"] = senior.RespuestaSenior(
            texto="Juan, listo.",
            acciones=[
                {"action": "ADD_ENTITY", "entityData": {"name": "Pedido"}},
                {"action": "ADD_ATTRIBUTE", "entityId": "Fantasma", "attributeData": {"name": "x", "type": "int"}},
            ],
        )
        with cliente.websocket_connect(_url(p, juan)) as a:
            _enviar(a, "@senior hacé cosas")
            m = _hasta(a, "CHAT_MESSAGE", cond=lambda q: q["mensaje"]["tipo"] == "senior_ai")["mensaje"]
            assert "no es válido" in m["texto"] and "Fantasma" in m["texto"]
        db = SL()
        assert [c.nombre for c in db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == p.id))] == ["Cliente"]
        db.close()

    def test_cola_responde_en_orden_sin_mezclar(self, cliente, SL, equipo, senior_falso):
        juan, maria = equipo
        p = _proyecto(SL, juan)
        senior_falso["demora"] = 0.2
        senior_falso["respuesta"] = lambda ctx: senior.RespuestaSenior(texto=f"{ctx.autor_nombre}, sobre: {ctx.pregunta}")
        with cliente.websocket_connect(_url(p, juan)) as a, cliente.websocket_connect(_url(p, maria)) as b:
            _hasta(a, "PRESENCE_LIST")
            _enviar(a, "@senior pregunta de Juan")
            _hasta(b, "CHAT_MESSAGE", cond=lambda q: q["mensaje"]["autor"]["nombre"] == "Juan")
            _enviar(b, "@senior pregunta de Maria")  # llega mientras el Senior todavía responde a Juan
            respuestas = [
                _hasta(a, "CHAT_MESSAGE", cond=lambda q: q["mensaje"]["tipo"] == "senior_ai")["mensaje"]["texto"]
                for _ in range(2)
            ]
        assert respuestas == ["Juan, sobre: @senior pregunta de Juan", "Maria, sobre: @senior pregunta de Maria"]
        # La segunda pregunta ve la primera respuesta en su historial (contexto en orden).
        segunda = senior_falso["llamadas"][1]
        assert any(m.es_ia and "pregunta de Juan" in m.texto for m in segunda.historial)

    def test_cambiar_modo_se_difunde_y_persiste(self, cliente, SL, equipo, senior_falso):
        juan, maria = equipo
        p = _proyecto(SL, juan)
        with cliente.websocket_connect(_url(p, juan)) as a, cliente.websocket_connect(_url(p, maria)) as b:
            _hasta(a, "PRESENCE_LIST")
            a.send_json({"type": "SET_AI_MODE", "payload": {"modo": "consultivo"}})
            cambio = _hasta(b, "AI_MODE_CHANGED")
            assert cambio == {"modo": "consultivo", "por": "Juan"}
        db = SL()
        assert db.get(Usuario, juan.id).grupo.modo_ia == "consultivo"
        db.close()


class TestChatPorGrupo:
    def test_integrantes_en_proyectos_distintos_comparten_el_chat(self, cliente, SL, equipo, senior_falso):
        juan, maria = equipo
        tienda = _proyecto(SL, juan, nombre="Tienda", clases=["Factura"])
        biblioteca = _proyecto(SL, maria, nombre="Biblioteca", clases=["Libro"])
        senior_falso["respuesta"] = lambda ctx: senior.RespuestaSenior(
            texto=f"{ctx.autor_nombre}, en {ctx.proyecto} veo {[c.nombre for c in ctx.diagrama.clases]}"
        )
        with cliente.websocket_connect(_url(tienda, juan)) as a, cliente.websocket_connect(_url(biblioteca, maria)) as b:
            lista = _hasta(a, "PRESENCE_LIST", cond=lambda q: len(q["usuarios"]) == 2)
            assert {u["proyecto"]["nombre"] for u in lista["usuarios"]} == {"Tienda", "Biblioteca"}
            _enviar(b, "hola Juan, estoy en la biblioteca")
            m = _hasta(a, "CHAT_MESSAGE")["mensaje"]
            assert m["autor"]["nombre"] == "Maria" and m["proyecto"]["nombre"] == "Biblioteca"
            # Juan ve la consulta de María al Senior y la respuesta, con el diagrama de SU proyecto.
            _enviar(b, "@senior ¿qué clases tengo?")
            r = _hasta(a, "CHAT_MESSAGE", cond=lambda q: q["mensaje"]["tipo"] == "senior_ai")["mensaje"]
            assert r["texto"] == "Maria, en Biblioteca veo ['Libro']"
        # Al volver desde otro proyecto del grupo, el historial es el mismo.
        with cliente.websocket_connect(_url(tienda, maria)) as c:
            textos = [m["texto"] for m in _hasta(c, "CHAT_HISTORY")["mensajes"]]
            assert "hola Juan, estoy en la biblioteca" in textos and len(textos) == 3

    def test_cambio_del_senior_va_al_proyecto_de_quien_pregunta(self, cliente, SL, equipo, senior_falso):
        juan, maria = equipo
        tienda = _proyecto(SL, juan, nombre="Tienda", clases=["Factura"])
        biblioteca = _proyecto(SL, maria, nombre="Biblioteca", clases=["Libro"])
        senior_falso["respuesta"] = senior.RespuestaSenior(
            texto="Maria, listo.", acciones=[{"action": "ADD_ENTITY", "entityData": {"name": "Prestamo"}}]
        )
        with cliente.websocket_connect(_url(tienda, juan)) as a, cliente.websocket_connect(_url(biblioteca, maria)) as b:
            _hasta(a, "PRESENCE_LIST", cond=lambda q: len(q["usuarios"]) == 2)
            _enviar(b, "@senior agregá Prestamo")
            ejecutado = _hasta(a, "AI_DIAGRAM_ACTION_EXECUTED")
            assert ejecutado["proyecto_id"] == biblioteca.id
        db = SL()
        nombres = lambda p: {c.nombre for c in db.scalars(select(ClaseUml).where(ClaseUml.id_proyecto == p.id))}
        assert nombres(biblioteca) == {"Libro", "Prestamo"} and nombres(tienda) == {"Factura"}
        db.close()

    def test_otro_grupo_no_ve_el_chat(self, cliente, SL, equipo, senior_falso):
        juan, _ = equipo
        pedro = _usuario(SL, "Pedro", grupo="Otro")
        p_juan = _proyecto(SL, juan, nombre="Tienda")
        p_pedro = _proyecto(SL, pedro, nombre="Taller")
        with cliente.websocket_connect(_url(p_juan, juan)) as a:
            _enviar(a, "secreto del grupo")
            _hasta(a, "CHAT_MESSAGE")
        with cliente.websocket_connect(_url(p_pedro, pedro)) as b:
            assert _hasta(b, "CHAT_HISTORY")["mensajes"] == []


class TestPuras:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("@senior ¿qué es esto?", True),
            ("Senior, ayudanos", True),
            ("oye senior una duda", True),
            ("hola @Senior", True),
            ("le pregunto al profe", False),
            ("seniority no cuenta", False),
        ],
    )
    def test_menciona_al_senior(self, texto, esperado):
        assert senior.menciona_al_senior(texto) is esperado

    def test_asegurar_saludo(self):
        assert senior.asegurar_saludo("Juan, claro.", "Juan Pérez") == "Juan, claro."
        assert senior.asegurar_saludo("¡Hola Juan! claro.", "Juan") == "¡Hola Juan! claro."
        assert senior.asegurar_saludo("Claro que sí.", "María José") == "@María, Claro que sí."

    def test_prompt_incluye_historial_con_autor_y_grupo(self):
        from app.schemas.diagrama import ClaseIO, DiagramaIO

        ctx = senior.ContextoSenior(
            grupo="G7",
            modo="automatico",
            diagrama=DiagramaIO(clases=[ClaseIO(id="c1", nombre="Cliente")], relaciones=[]),
            historial=[
                senior.MensajeHistorial("Ana", False, "@senior creá Cliente"),
                senior.MensajeHistorial("Senior", True, "Ana, creé Cliente."),
            ],
            resumen="- Se decidió usar PostgreSQL",
            autor_id=9,
            autor_nombre="Ana",
            pregunta="¿Y si le agregamos teléfono a la clase anterior?",
        )
        system, texto = senior.construir_prompt(ctx)
        assert "Grupo: G7" in texto
        assert "[Ana]: @senior creá Cliente" in texto and "[Senior]: Ana, creé Cliente." in texto
        assert '"name": "Cliente"' in texto
        assert "id de usuario 9" in texto
        assert "Se decidió usar PostgreSQL" in texto
        assert "MODO AUTOMÁTICO" in system


def test_hilo_no_queda_colgado():
    assert threading.active_count() < 50
