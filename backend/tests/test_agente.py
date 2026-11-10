import uuid

from app.models.usuario import RolUsuario
from app.models.clase_uml import ClaseUml
from app.services import agente


def _mock_llamada(monkeypatch, nombre_tool=None, argumentos=None, texto=None):
    monkeypatch.setattr(agente, "_llamar_openai_agente", lambda mensajes: (nombre_tool, argumentos, texto))


def _mock_llamada_capturando(monkeypatch, resultado):
    capturado = {}

    def _fake(mensajes):
        capturado["mensajes"] = mensajes
        return resultado

    monkeypatch.setattr(agente, "_llamar_openai_agente", _fake)
    return capturado


def _crear_clase(db_session, proyecto, nombre="Cliente"):
    clase = ClaseUml(id=str(uuid.uuid4()), id_proyecto=proyecto.id, nombre=nombre)
    db_session.add(clase)
    db_session.commit()
    db_session.refresh(clase)
    return clase


class TestAcciones:
    def test_crear_clase(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, "crear_clase", {"nombre_clase": "Pedido", "atributos": []})

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "crea una clase Pedido", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["accion"]["accion"] == "crear_clase"
        assert datos["accion"]["nombre_clase"] == "Pedido"
        assert "Pedido" in datos["texto"]

    def test_agregar_atributo(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clase = _crear_clase(db_session, proyecto, "Cliente")
        _mock_llamada(
            monkeypatch,
            "agregar_atributo",
            {"nombre_clase": "Cliente", "nombre": "telefono", "tipo": "String", "visibilidad": "PUBLICO"},
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "agregale el atributo telefono a Cliente", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["accion"]["id_clase"] == clase.id

    def test_eliminar_clase(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clase = _crear_clase(db_session, proyecto, "Pedido")
        _mock_llamada(monkeypatch, "eliminar_clase", {"nombre_clase": "Pedido"})

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "elimina la clase Pedido", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        assert resp.json()["accion"]["id_clase"] == clase.id

    def test_crear_relacion(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        origen = _crear_clase(db_session, proyecto, "Usuario")
        destino = _crear_clase(db_session, proyecto, "Pedido")
        _mock_llamada(
            monkeypatch,
            "crear_relacion",
            {
                "nombre_clase_origen": "Usuario",
                "nombre_clase_destino": "Pedido",
                "tipo_relacion": "ASOCIACION",
                "multiplicidad_origen": "1",
                "multiplicidad_destino": "0..*",
            },
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "relaciona Usuario con Pedido", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["accion"]["id_clase_origen"] == origen.id
        assert datos["accion"]["id_clase_destino"] == destino.id

    def test_renombrar_clase(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clase = _crear_clase(db_session, proyecto, "Cliente")
        _mock_llamada(monkeypatch, "renombrar_clase", {"nombre_actual": "Cliente", "nombre_nuevo": "Usuario"})

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "cambia el nombre de Cliente a Usuario", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        assert resp.json()["accion"]["id_clase"] == clase.id


class TestPreguntas:
    def test_pregunta_sobre_uml(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, texto="La agregación es un todo-parte sin dependencia de vida.")

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "¿qué es agregación en UML?", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["accion"] is None
        assert "agregación" in datos["texto"].lower()


class TestNoRompeElDiagrama:
    def test_clase_no_encontrada_es_200(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(
            monkeypatch,
            "agregar_atributo",
            {"nombre_clase": "Factura", "nombre": "monto", "tipo": "float", "visibilidad": "PRIVADO"},
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "agregale monto a Factura", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["accion"] is None
        assert "Factura" in datos["texto"]

    def test_nombre_duplicado_es_200(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _crear_clase(db_session, proyecto, "Cliente")
        _mock_llamada(monkeypatch, "crear_clase", {"nombre_clase": "cliente", "atributos": []})

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "crea una clase Cliente", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        assert resp.json()["accion"] is None

    def test_comando_no_mapeable_sin_texto_del_modelo(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch)  # nombre_tool=None, argumentos=None, texto=None

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "asdkjaslkdj", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        assert resp.json()["accion"] is None
        assert resp.json()["texto"]


class TestHistorial:
    def test_historial_se_mapea_a_roles_openai(
        self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch
    ):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        capturado = _mock_llamada_capturando(monkeypatch, (None, None, "listo"))

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={
                "mensaje": "y ahora renombrala",
                "historial": [
                    {"rol": "usuario", "texto": "crea una clase Cliente"},
                    {"rol": "agente", "texto": 'Se creó la clase "Cliente".'},
                ],
            },
            headers=headers(admin),
        )
        assert resp.status_code == 200
        mensajes = capturado["mensajes"]
        assert mensajes[0]["role"] == "system"
        assert mensajes[1] == {"role": "user", "content": "crea una clase Cliente"}
        assert mensajes[2] == {"role": "assistant", "content": 'Se creó la clase "Cliente".'}
        assert mensajes[3] == {"role": "user", "content": "y ahora renombrala"}


class TestErroresGenerales:
    def test_openai_no_disponible(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)

        def _falla(mensajes):
            raise agente.ComandoVozNoDisponibleError("timeout")

        monkeypatch.setattr(agente, "_llamar_openai_agente", _falla)

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "crea una clase Cliente", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 503

    def test_sin_acceso(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        otro = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, "crear_clase", {"nombre_clase": "Pedido", "atributos": []})

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "crea una clase Pedido", "historial": []},
            headers=headers(otro),
        )
        assert resp.status_code == 403

    def test_proyecto_inexistente(self, client, db_session, crear_usuario, headers, monkeypatch):
        admin = crear_usuario()
        _mock_llamada(monkeypatch, "crear_clase", {"nombre_clase": "Pedido", "atributos": []})

        resp = client.post(
            "/proyectos/999999/agente",
            json={"mensaje": "crea una clase Pedido", "historial": []},
            headers=headers(admin),
        )
        assert resp.status_code == 404

    def test_colaborador_activo_puede_usarlo(
        self, client, db_session, crear_usuario, crear_proyecto, agregar_colaborador, headers, monkeypatch
    ):
        admin = crear_usuario()
        colaborador = crear_usuario(rol=RolUsuario.COLABORADOR)
        proyecto = crear_proyecto(admin)
        agregar_colaborador(proyecto, colaborador)
        _mock_llamada(monkeypatch, "crear_clase", {"nombre_clase": "Pedido", "atributos": []})

        resp = client.post(
            f"/proyectos/{proyecto.id}/agente",
            json={"mensaje": "crea una clase Pedido", "historial": []},
            headers=headers(colaborador),
        )
        assert resp.status_code == 200
