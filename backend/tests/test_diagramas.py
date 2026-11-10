from app.models.usuario import RolUsuario


def _url(proyecto_id: int) -> str:
    return f"/proyectos/{proyecto_id}/diagrama"


def test_diagrama_vacio_para_proyecto_nuevo(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.get(_url(proyecto.id), headers=headers(admin))

    assert resp.status_code == 200
    assert resp.json() == {"clases": [], "relaciones": []}


def test_guardar_y_obtener_clase_con_atributos_y_metodos(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    payload = {
        "clases": [
            {
                "id": "clase-1",
                "nombre": "Cliente",
                "estereotipo": "entity",
                "es_abstracta": False,
                "pos_x": 120.5,
                "pos_y": 40.0,
                "atributos": [
                    {"id": "attr-1", "nombre": "nombre", "tipo": "str", "visibilidad": "PRIVADO", "orden": 0}
                ],
                "metodos": [
                    {
                        "id": "met-1",
                        "nombre": "saludar",
                        "parametros": "",
                        "tipo_retorno": "str",
                        "visibilidad": "PUBLICO",
                        "orden": 0,
                    }
                ],
            }
        ],
        "relaciones": [],
    }

    put_resp = client.put(_url(proyecto.id), json=payload, headers=headers(admin))
    assert put_resp.status_code == 200

    get_resp = client.get(_url(proyecto.id), headers=headers(admin))
    assert get_resp.status_code == 200
    datos = get_resp.json()

    assert len(datos["clases"]) == 1
    clase = datos["clases"][0]
    assert clase["nombre"] == "Cliente"
    assert clase["estereotipo"] == "entity"
    assert clase["es_abstracta"] is False
    assert clase["pos_x"] == 120.5
    assert clase["pos_y"] == 40.0
    assert len(clase["atributos"]) == 1
    assert clase["atributos"][0]["nombre"] == "nombre"
    assert clase["atributos"][0]["visibilidad"] == "PRIVADO"
    assert len(clase["metodos"]) == 1
    assert clase["metodos"][0]["nombre"] == "saludar"
    assert clase["metodos"][0]["tipo_retorno"] == "str"


def test_guardar_relacion_entre_dos_clases(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    payload = {
        "clases": [
            {"id": "clase-a", "nombre": "A", "estereotipo": None, "es_abstracta": False, "pos_x": 0, "pos_y": 0},
            {"id": "clase-b", "nombre": "B", "estereotipo": None, "es_abstracta": False, "pos_x": 200, "pos_y": 0},
        ],
        "relaciones": [
            {
                "id": "rel-1",
                "id_clase_origen": "clase-a",
                "id_clase_destino": "clase-b",
                "tipo": "HERENCIA",
                "etiqueta": "hereda de",
                "multiplicidad_origen": "1",
                "multiplicidad_destino": "0..*",
                "handle_origen": "right",
                "handle_destino": "left",
            }
        ],
    }

    put_resp = client.put(_url(proyecto.id), json=payload, headers=headers(admin))
    assert put_resp.status_code == 200

    datos = client.get(_url(proyecto.id), headers=headers(admin)).json()
    assert len(datos["relaciones"]) == 1
    relacion = datos["relaciones"][0]
    assert relacion["tipo"] == "HERENCIA"
    assert relacion["etiqueta"] == "hereda de"
    assert relacion["multiplicidad_origen"] == "1"
    assert relacion["multiplicidad_destino"] == "0..*"
    assert relacion["id_clase_origen"] == "clase-a"
    assert relacion["id_clase_destino"] == "clase-b"


def test_colaborador_activo_puede_ver_y_guardar(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers
):
    admin = crear_usuario()
    colaborador = crear_usuario(rol=RolUsuario.COLABORADOR)
    proyecto = crear_proyecto(admin)
    agregar_colaborador(proyecto, colaborador, activo=True)

    get_resp = client.get(_url(proyecto.id), headers=headers(colaborador))
    assert get_resp.status_code == 200

    put_resp = client.put(_url(proyecto.id), json={"clases": [], "relaciones": []}, headers=headers(colaborador))
    assert put_resp.status_code == 200


def test_colaborador_inactivo_no_tiene_acceso(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers
):
    admin = crear_usuario()
    colaborador = crear_usuario(rol=RolUsuario.COLABORADOR)
    proyecto = crear_proyecto(admin)
    agregar_colaborador(proyecto, colaborador, activo=False)

    resp = client.get(_url(proyecto.id), headers=headers(colaborador))
    assert resp.status_code == 403


def test_usuario_sin_relacion_no_tiene_acceso(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    otro = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.get(_url(proyecto.id), headers=headers(otro))
    assert resp.status_code == 403


def test_proyecto_inexistente_devuelve_404(client, crear_usuario, headers):
    admin = crear_usuario()

    resp = client.get(_url(999999), headers=headers(admin))
    assert resp.status_code == 404


def test_guardar_diagrama_reemplaza_contenido_anterior(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    primero = {
        "clases": [
            {"id": "clase-a", "nombre": "A", "estereotipo": None, "es_abstracta": False, "pos_x": 0, "pos_y": 0}
        ],
        "relaciones": [],
    }
    client.put(_url(proyecto.id), json=primero, headers=headers(admin))

    segundo = {
        "clases": [
            {"id": "clase-b", "nombre": "B", "estereotipo": None, "es_abstracta": False, "pos_x": 0, "pos_y": 0}
        ],
        "relaciones": [],
    }
    client.put(_url(proyecto.id), json=segundo, headers=headers(admin))

    datos = client.get(_url(proyecto.id), headers=headers(admin)).json()
    nombres = [c["nombre"] for c in datos["clases"]]
    assert nombres == ["B"]


def test_sin_token_devuelve_401(client, crear_usuario, crear_proyecto):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.get(_url(proyecto.id))
    assert resp.status_code == 401


def test_nombres_de_clase_duplicados_devuelve_409(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    payload = {
        "clases": [
            {"id": "clase-a", "nombre": "Cliente", "estereotipo": None, "es_abstracta": False, "pos_x": 0, "pos_y": 0},
            {"id": "clase-b", "nombre": "cliente", "estereotipo": None, "es_abstracta": False, "pos_x": 0, "pos_y": 0},
        ],
        "relaciones": [],
    }

    resp = client.put(_url(proyecto.id), json=payload, headers=headers(admin))
    assert resp.status_code == 409

    # El payload inválido no debe haber tocado el diagrama existente.
    datos = client.get(_url(proyecto.id), headers=headers(admin)).json()
    assert datos == {"clases": [], "relaciones": []}


def test_relacion_a_clase_fuera_del_payload_devuelve_400(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    payload = {
        "clases": [
            {"id": "clase-a", "nombre": "A", "estereotipo": None, "es_abstracta": False, "pos_x": 0, "pos_y": 0},
        ],
        "relaciones": [
            {
                "id": "rel-1",
                "id_clase_origen": "clase-a",
                "id_clase_destino": "clase-inexistente",
                "tipo": "ASOCIACION",
                "etiqueta": None,
                "multiplicidad_origen": None,
                "multiplicidad_destino": None,
                "handle_origen": None,
                "handle_destino": None,
            }
        ],
    }

    resp = client.put(_url(proyecto.id), json=payload, headers=headers(admin))
    assert resp.status_code == 400


def test_multiplicidad_invalida_devuelve_400(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    payload = {
        "clases": [
            {"id": "clase-a", "nombre": "A", "estereotipo": None, "es_abstracta": False, "pos_x": 0, "pos_y": 0},
            {"id": "clase-b", "nombre": "B", "estereotipo": None, "es_abstracta": False, "pos_x": 0, "pos_y": 0},
        ],
        "relaciones": [
            {
                "id": "rel-1",
                "id_clase_origen": "clase-a",
                "id_clase_destino": "clase-b",
                "tipo": "ASOCIACION",
                "etiqueta": None,
                "multiplicidad_origen": "muchos",
                "multiplicidad_destino": "0..*",
                "handle_origen": None,
                "handle_destino": None,
            }
        ],
    }

    resp = client.put(_url(proyecto.id), json=payload, headers=headers(admin))
    assert resp.status_code == 400
    assert "muchos" in resp.json()["detail"]


def _payload_con_forma(forma, desvio_x=None, desvio_y=None):
    return {
        "clases": [
            {"id": "clase-a", "nombre": "A", "pos_x": 0, "pos_y": 0},
            {"id": "clase-b", "nombre": "B", "pos_x": 300, "pos_y": 0},
        ],
        "relaciones": [
            {
                "id": "rel-1",
                "id_clase_origen": "clase-a",
                "id_clase_destino": "clase-b",
                "tipo": "ASOCIACION",
                "forma": forma,
                "desvio_x": desvio_x,
                "desvio_y": desvio_y,
            }
        ],
    }


def test_forma_y_desvio_de_relacion_se_persisten(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.put(_url(proyecto.id), json=_payload_con_forma("CURVA", 12.5, -40), headers=headers(admin))
    assert resp.status_code == 200

    relacion = client.get(_url(proyecto.id), headers=headers(admin)).json()["relaciones"][0]
    assert relacion["forma"] == "CURVA"
    assert relacion["desvio_x"] == 12.5
    assert relacion["desvio_y"] == -40


def test_relacion_sin_forma_queda_en_null(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    client.put(_url(proyecto.id), json=_payload_con_forma(None), headers=headers(admin))

    relacion = client.get(_url(proyecto.id), headers=headers(admin)).json()["relaciones"][0]
    assert relacion["forma"] is None
    assert relacion["desvio_x"] is None
    assert relacion["desvio_y"] is None


def test_forma_invalida_devuelve_422(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.put(_url(proyecto.id), json=_payload_con_forma("ZIGZAG"), headers=headers(admin))
    assert resp.status_code == 422
