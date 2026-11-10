"""Segundo parcial (RF-RT-01/02): registro con grupo y tableros por grupo."""
import pytest


def _registrar(client, nombre, grupo):
    resp = client.post(
        "/auth/registro",
        json={"nombre_completo": nombre, "email": f"{abs(hash(nombre + grupo))}@g.com", "password": "clave12345", "nombre_grupo": grupo},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_registro_con_grupo_y_union_por_nombre(client):
    h_juan = _registrar(client, "Juan", "Grupo  Siete")
    h_maria = _registrar(client, "Maria", "grupo siete")
    juan = client.get("/usuarios/me", headers=h_juan).json()
    maria = client.get("/usuarios/me", headers=h_maria).json()
    assert juan["nombre_grupo"] == "Grupo Siete"
    assert juan["id_grupo"] == maria["id_grupo"]


def test_integrantes_comparten_tableros_y_ajenos_no(client):
    h_juan = _registrar(client, "Juan", "G1")
    h_maria = _registrar(client, "Maria", "G1")
    h_pedro = _registrar(client, "Pedro", "G2")
    proyecto = client.post("/proyectos", json={"nombre": "Tienda"}, headers=h_juan).json()

    lista_maria = client.get("/proyectos", headers=h_maria).json()
    assert [p["nombre"] for p in lista_maria] == ["Tienda"]
    assert lista_maria[0]["rol_en_proyecto"] == "COLABORADOR"
    assert client.get(f"/proyectos/{proyecto['id']}/diagrama", headers=h_maria).status_code == 200

    assert client.get("/proyectos", headers=h_pedro).json() == []
    assert client.get(f"/proyectos/{proyecto['id']}/diagrama", headers=h_pedro).status_code == 403
    # Solo el dueño administra el proyecto (editar/eliminar/colaboradores).
    assert client.put(f"/proyectos/{proyecto['id']}", json={"nombre": "X"}, headers=h_maria).status_code == 403


def test_cambiar_de_grupo_desde_el_perfil(client):
    h = _registrar(client, "Ana", "Viejo")
    resp = client.put("/usuarios/me", json={"nombre_grupo": "Nuevo"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["nombre_grupo"] == "Nuevo"


def test_registro_sin_grupo_sigue_funcionando(client):
    resp = client.post(
        "/auth/registro", json={"nombre_completo": "Sin", "email": "sin@g.com", "password": "clave12345"}
    )
    assert resp.status_code == 201


def test_login_con_nombre_y_grupo(client):
    _registrar(client, "Juan Pérez", "Los Modeladores")
    resp = client.post(
        "/auth/login-grupo",
        json={"nombre_completo": "juan perez", "nombre_grupo": "los  modeladores", "password": "clave12345"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    yo = client.get("/usuarios/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert yo["nombre_completo"] == "Juan Pérez" and yo["nombre_grupo"] == "Los Modeladores"


@pytest.mark.parametrize(
    "nombre,grupo,password",
    [("Juan Pérez", "Otro grupo", "clave12345"), ("Pedro", "Los Modeladores", "clave12345"), ("Juan Pérez", "Los Modeladores", "mala")],
)
def test_login_con_nombre_y_grupo_incorrecto(client, nombre, grupo, password):
    _registrar(client, "Juan Pérez", "Los Modeladores")
    resp = client.post("/auth/login-grupo", json={"nombre_completo": nombre, "nombre_grupo": grupo, "password": password})
    assert resp.status_code == 401


def test_nombre_unico_dentro_del_grupo(client):
    _registrar(client, "Ana", "G")
    resp = client.post(
        "/auth/registro",
        json={"nombre_completo": "ana", "email": "otra@g.com", "password": "clave12345", "nombre_grupo": "g"},
    )
    assert resp.status_code == 409
    # En otro grupo sí se puede.
    assert client.post(
        "/auth/registro",
        json={"nombre_completo": "Ana", "email": "otra@g.com", "password": "clave12345", "nombre_grupo": "H"},
    ).status_code == 201
