import pytest

from app.models.usuario import RolUsuario
from app.models.clase_uml import ClaseUml
from app.services import comandos_voz


def _mock_llamada(monkeypatch, nombre_tool, argumentos):
    monkeypatch.setattr(
        comandos_voz, "_llamar_openai", lambda texto, prompt: (nombre_tool, argumentos)
    )


def _crear_clase(db_session, proyecto, nombre="Cliente"):
    import uuid

    clase = ClaseUml(id=str(uuid.uuid4()), id_proyecto=proyecto.id, nombre=nombre)
    db_session.add(clase)
    db_session.commit()
    db_session.refresh(clase)
    return clase


class TestCrearClase:
    def test_sin_atributos(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, "crear_clase", {"nombre_clase": "Pedido", "atributos": []})

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "crea una clase Pedido"},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["accion"] == "crear_clase"
        assert datos["nombre_clase"] == "Pedido"
        assert datos["atributos"] == []

    def test_con_atributos(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(
            monkeypatch,
            "crear_clase",
            {
                "nombre_clase": "Cliente",
                "atributos": [
                    {"nombre": "nombre", "tipo": "String", "visibilidad": "PRIVADO"},
                    {"nombre": "correo", "tipo": "String", "visibilidad": "PRIVADO"},
                ],
            },
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "crea una clase Cliente con atributos nombre y correo"},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert len(datos["atributos"]) == 2
        assert all("id" not in a for a in datos["atributos"])

    def test_nombre_duplicado(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _crear_clase(db_session, proyecto, "Cliente")
        _mock_llamada(monkeypatch, "crear_clase", {"nombre_clase": "cliente", "atributos": []})

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "crea una clase Cliente"},
            headers=headers(admin),
        )
        assert resp.status_code == 422


class TestAgregarAtributo:
    def test_exitoso(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clase = _crear_clase(db_session, proyecto, "Cliente")
        _mock_llamada(
            monkeypatch,
            "agregar_atributo",
            {"nombre_clase": "Cliente", "nombre": "telefono", "tipo": "String", "visibilidad": "PUBLICO"},
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "agrega el atributo telefono a la clase Cliente"},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["accion"] == "agregar_atributo"
        assert datos["id_clase"] == clase.id
        assert datos["atributo"]["nombre"] == "telefono"

    def test_clase_no_encontrada(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(
            monkeypatch,
            "agregar_atributo",
            {"nombre_clase": "Factura", "nombre": "monto", "tipo": "float", "visibilidad": "PRIVADO"},
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "agrega el atributo monto a la clase Factura"},
            headers=headers(admin),
        )
        assert resp.status_code == 422
        assert "Factura" in resp.json()["detail"]


class TestEliminarClase:
    def test_exitoso(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clase = _crear_clase(db_session, proyecto, "Pedido")
        _mock_llamada(monkeypatch, "eliminar_clase", {"nombre_clase": "Pedido"})

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "elimina la clase Pedido"},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        assert resp.json()["id_clase"] == clase.id


class TestCrearRelacion:
    def test_con_multiplicidad(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
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
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "crea una relacion de asociacion entre Usuario y Pedido"},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["id_clase_origen"] == origen.id
        assert datos["id_clase_destino"] == destino.id
        assert datos["tipo"] == "ASOCIACION"

    def test_sin_multiplicidad(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _crear_clase(db_session, proyecto, "Usuario")
        _crear_clase(db_session, proyecto, "Pedido")
        _mock_llamada(
            monkeypatch,
            "crear_relacion",
            {
                "nombre_clase_origen": "Usuario",
                "nombre_clase_destino": "Pedido",
                "tipo_relacion": "HERENCIA",
                "multiplicidad_origen": None,
                "multiplicidad_destino": None,
            },
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "Pedido hereda de Usuario"},
            headers=headers(admin),
        )
        assert resp.status_code == 200


class TestRenombrarClase:
    def test_exitoso(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        clase = _crear_clase(db_session, proyecto, "Cliente")
        _mock_llamada(monkeypatch, "renombrar_clase", {"nombre_actual": "Cliente", "nombre_nuevo": "Usuario"})

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "cambia el nombre de la clase Cliente a Usuario"},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["id_clase"] == clase.id
        assert datos["nombre_anterior"] == "Cliente"
        assert datos["nombre_nuevo"] == "Usuario"


class TestErroresGenerales:
    def test_comando_no_mapeable(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, None, None)

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "cambia el color de fondo"},
            headers=headers(admin),
        )
        assert resp.status_code == 422

    def test_argumentos_invalidos(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        _crear_clase(db_session, proyecto, "Usuario")
        _crear_clase(db_session, proyecto, "Pedido")
        _mock_llamada(
            monkeypatch,
            "crear_relacion",
            {
                "nombre_clase_origen": "Usuario",
                "nombre_clase_destino": "Pedido",
                "tipo_relacion": "NO_EXISTE",
                "multiplicidad_origen": None,
                "multiplicidad_destino": None,
            },
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "algo raro"},
            headers=headers(admin),
        )
        assert resp.status_code == 422

    def test_openai_no_disponible(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)

        def _falla(texto, prompt):
            raise comandos_voz.ComandoVozNoDisponibleError("timeout")

        monkeypatch.setattr(comandos_voz, "_llamar_openai", _falla)

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "crea una clase Cliente"},
            headers=headers(admin),
        )
        assert resp.status_code == 503

    def test_sin_acceso(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        otro = crear_usuario()
        proyecto = crear_proyecto(admin)
        _mock_llamada(monkeypatch, "crear_clase", {"nombre_clase": "Pedido", "atributos": []})

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "crea una clase Pedido"},
            headers=headers(otro),
        )
        assert resp.status_code == 403

    def test_proyecto_inexistente(self, client, db_session, crear_usuario, headers, monkeypatch):
        admin = crear_usuario()
        _mock_llamada(monkeypatch, "crear_clase", {"nombre_clase": "Pedido", "atributos": []})

        resp = client.post(
            "/proyectos/999999/comandos-voz",
            json={"texto": "crea una clase Pedido"},
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
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "crea una clase Pedido"},
            headers=headers(colaborador),
        )
        assert resp.status_code == 200


# --- Lenguaje natural: acción compuesta `modificar_diagrama` ----------------
# `_manejar_modificar_diagrama` es una función pura: se prueba directo contra
# un `DiagramaIO` armado a mano, sin BD ni OpenAI; y un test pasa por HTTP.

from app.schemas.diagrama import AtributoIO, ClaseIO, DiagramaIO, RelacionIO  # noqa: E402
from app.services.comandos_voz import ComandoVozInvalidoError, _manejar_modificar_diagrama  # noqa: E402


def _atr(nombre, tipo="String"):
    return {"nombre": nombre, "tipo": tipo, "visibilidad": "PRIVADO"}


def _rel(origen, destino, tipo="ASOCIACION", mult_origen="1", mult_destino="0..*", etiqueta=None):
    return {
        "razonamiento": "prueba",
        "tipo": tipo,
        "clase_origen": origen,
        "multiplicidad_junto_a_clase_origen": mult_origen,
        "clase_destino": destino,
        "multiplicidad_junto_a_clase_destino": mult_destino,
        "etiqueta": etiqueta,
    }


def _modificar(clases_nuevas=(), existentes_attrs=(), relaciones=()):
    return {
        "clases_nuevas": list(clases_nuevas),
        "atributos_para_clases_existentes": list(existentes_attrs),
        "relaciones": list(relaciones),
    }


class TestModificarDiagrama:
    def test_dos_clases_nuevas_relacionadas(self):
        accion = _manejar_modificar_diagrama(
            _modificar(
                [
                    {"nombre": "Cliente", "atributos": [_atr("nombre"), _atr("correo")]},
                    {"nombre": "Pedido", "atributos": [_atr("fecha", "Date"), _atr("total", "double")]},
                ],
                relaciones=[_rel("Cliente", "Pedido", etiqueta="realiza")],
            ),
            DiagramaIO(),
        )
        assert [c.nombre for c in accion.clases_nuevas] == ["Cliente", "Pedido"]
        assert len(accion.clases_nuevas[1].atributos) == 2
        [relacion] = accion.relaciones
        assert relacion.origen.id_clase is None and relacion.origen.nombre_clase == "Cliente"
        assert relacion.destino.id_clase is None and relacion.destino.nombre_clase == "Pedido"
        assert (relacion.multiplicidad_origen, relacion.multiplicidad_destino) == ("1", "0..*")
        assert relacion.etiqueta == "realiza"
        assert accion.advertencias == []
        assert "Cliente" in accion.resumen and "asociación" in accion.resumen

    def test_relacion_con_clase_existente_ignora_tildes(self):
        diagrama = DiagramaIO(clases=[ClaseIO(id="c-dir", nombre="Dirección")])
        accion = _manejar_modificar_diagrama(
            _modificar([{"nombre": "Persona", "atributos": []}], relaciones=[_rel("Persona", "direccion")]),
            diagrama,
        )
        [relacion] = accion.relaciones
        assert relacion.destino.id_clase == "c-dir"
        assert relacion.destino.nombre_clase == "Dirección"

    def test_clase_nueva_que_ya_existe_agrega_atributos(self):
        diagrama = DiagramaIO(
            clases=[ClaseIO(id="c-prod", nombre="Producto", atributos=[AtributoIO(id="a1", nombre="precio")])]
        )
        accion = _manejar_modificar_diagrama(
            _modificar([{"nombre": "producto", "atributos": [_atr("precio", "double"), _atr("stock", "int")]}]),
            diagrama,
        )
        assert accion.clases_nuevas == []
        [grupo] = accion.atributos_agregados
        assert grupo.id_clase == "c-prod"
        assert [a.nombre for a in grupo.atributos] == ["stock"]
        assert any("precio" in a for a in accion.advertencias)

    def test_relacion_a_clase_desconocida_se_descarta(self):
        accion = _manejar_modificar_diagrama(
            _modificar([{"nombre": "Pedido", "atributos": []}], relaciones=[_rel("Cliente", "Pedido")]),
            DiagramaIO(),
        )
        assert accion.relaciones == []
        assert any("Cliente" in a for a in accion.advertencias)

    def test_relacion_ya_existente_o_repetida_se_descarta(self):
        diagrama = DiagramaIO(
            clases=[ClaseIO(id="c1", nombre="Cliente"), ClaseIO(id="c2", nombre="Pedido")],
            relaciones=[RelacionIO(id="r1", id_clase_origen="c1", id_clase_destino="c2", tipo="ASOCIACION")],
        )
        accion = _manejar_modificar_diagrama(
            _modificar(
                [{"nombre": "Factura", "atributos": []}],
                relaciones=[
                    _rel("Pedido", "Cliente"),  # ya existe, con el orden invertido
                    _rel("Pedido", "Factura"),
                    _rel("Pedido", "Factura"),  # repetida en el mismo comando
                ],
            ),
            diagrama,
        )
        assert len(accion.relaciones) == 1
        assert accion.relaciones[0].destino.nombre_clase == "Factura"

    def test_herencia_sin_multiplicidad(self):
        diagrama = DiagramaIO(clases=[ClaseIO(id="c1", nombre="Cliente")])
        accion = _manejar_modificar_diagrama(
            _modificar(
                [{"nombre": "ClienteVip", "atributos": [_atr("descuento", "double")]}],
                relaciones=[_rel("ClienteVip", "Cliente", tipo="HERENCIA", etiqueta="es un")],
            ),
            diagrama,
        )
        [relacion] = accion.relaciones
        assert relacion.tipo.value == "HERENCIA"
        assert relacion.multiplicidad_origen is None and relacion.multiplicidad_destino is None
        assert relacion.etiqueta is None
        assert relacion.destino.id_clase == "c1"

    def test_nombre_en_pascal_case_y_matching_sin_espacios(self):
        diagrama = DiagramaIO(clases=[ClaseIO(id="c1", nombre="Pedido")])
        accion = _manejar_modificar_diagrama(
            _modificar(
                [{"nombre": "detalle pedido", "atributos": []}],
                relaciones=[_rel("Pedido", "Detalle Pedido", tipo="COMPOSICION", mult_destino="1..*")],
            ),
            diagrama,
        )
        assert accion.clases_nuevas[0].nombre == "DetallePedido"
        [relacion] = accion.relaciones
        assert relacion.destino.nombre_clase == "DetallePedido"
        assert relacion.tipo.value == "COMPOSICION"

    def test_multiplicidad_invalida_queda_vacia(self):
        accion = _manejar_modificar_diagrama(
            _modificar(
                [{"nombre": "A", "atributos": []}, {"nombre": "B", "atributos": []}],
                relaciones=[_rel("A", "B", mult_origen="2..5")],
            ),
            DiagramaIO(),
        )
        assert accion.relaciones[0].multiplicidad_origen is None
        assert accion.relaciones[0].multiplicidad_destino == "0..*"

    def test_sin_nada_aplicable_es_error(self):
        with pytest.raises(ComandoVozInvalidoError):
            _manejar_modificar_diagrama(_modificar(relaciones=[_rel("X", "Y")]), DiagramaIO())

    def test_por_http_con_clase_existente(self, client, db_session, crear_usuario, crear_proyecto, headers, monkeypatch):
        admin = crear_usuario()
        proyecto = crear_proyecto(admin)
        cliente = _crear_clase(db_session, proyecto, "Cliente")
        _mock_llamada(
            monkeypatch,
            "modificar_diagrama",
            _modificar(
                [{"nombre": "Pedido", "atributos": [_atr("total", "double")]}],
                relaciones=[_rel("Cliente", "Pedido")],
            ),
        )

        resp = client.post(
            f"/proyectos/{proyecto.id}/comandos-voz",
            json={"texto": "agrega un pedido con total"},
            headers=headers(admin),
        )
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["accion"] == "modificar_diagrama"
        assert datos["clases_nuevas"][0]["nombre"] == "Pedido"
        assert datos["relaciones"][0]["origen"] == {"id_clase": cliente.id, "nombre_clase": "Cliente"}
        assert datos["relaciones"][0]["destino"] == {"id_clase": None, "nombre_clase": "Pedido"}
