from app.models.usuario import RolUsuario


def _url_colaboradores(proyecto_id: int) -> str:
    return f"/proyectos/{proyecto_id}/colaboradores"


# --------------------------------------------------------------------------
# CU06 — búsqueda de usuarios
# --------------------------------------------------------------------------


def test_buscar_por_nombre_parcial(client, crear_usuario, headers, db_session):
    yo = crear_usuario()
    encontrado = crear_usuario()
    encontrado.nombre_completo = "Ana Beatriz Gómez"
    db_session.commit()

    resp = client.get("/usuarios/buscar", params={"q": "beatriz"}, headers=headers(yo))
    assert resp.status_code == 200
    nombres = [u["nombre_completo"] for u in resp.json()]
    assert "Ana Beatriz Gómez" in nombres


def test_buscar_por_email_parcial(client, crear_usuario, headers, db_session):
    yo = crear_usuario()
    encontrado = crear_usuario()
    encontrado.email = "persona.especial@test.com"
    db_session.commit()

    resp = client.get("/usuarios/buscar", params={"q": "especial"}, headers=headers(yo))
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert "persona.especial@test.com" in emails


def test_buscar_excluye_al_propio_usuario(client, crear_usuario, headers, db_session):
    yo = crear_usuario()
    yo.nombre_completo = "Zebra Unico"
    db_session.commit()

    resp = client.get("/usuarios/buscar", params={"q": "zebra"}, headers=headers(yo))
    assert resp.status_code == 200
    assert resp.json() == []


def test_buscar_con_proyecto_id_excluye_colaboradores_activos(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers, db_session
):
    admin = crear_usuario()
    candidato = crear_usuario()
    candidato.nombre_completo = "Candidato Buscable"
    db_session.commit()
    proyecto = crear_proyecto(admin)
    agregar_colaborador(proyecto, candidato, activo=True)

    # Sin proyecto_id: aparece.
    sin_filtro = client.get("/usuarios/buscar", params={"q": "buscable"}, headers=headers(admin))
    assert any(u["id"] == candidato.id for u in sin_filtro.json())

    # Con proyecto_id: ya es colaborador activo, no debe aparecer.
    con_filtro = client.get(
        "/usuarios/buscar", params={"q": "buscable", "proyecto_id": proyecto.id}, headers=headers(admin)
    )
    assert all(u["id"] != candidato.id for u in con_filtro.json())


def test_buscar_con_proyecto_id_ajeno_devuelve_403(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    ajeno = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.get(
        "/usuarios/buscar", params={"q": "algo", "proyecto_id": proyecto.id}, headers=headers(ajeno)
    )
    assert resp.status_code == 403


def test_buscar_con_texto_vacio_devuelve_lista_vacia(client, crear_usuario, headers):
    yo = crear_usuario()
    resp = client.get("/usuarios/buscar", params={"q": "   "}, headers=headers(yo))
    assert resp.status_code == 200
    assert resp.json() == []


# --------------------------------------------------------------------------
# CU05 — agregar / listar / quitar colaboradores
# --------------------------------------------------------------------------


def test_agregar_colaborador_nuevo(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    candidato = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.post(_url_colaboradores(proyecto.id), json={"usuario_id": candidato.id}, headers=headers(admin))
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["activo"] is True
    assert cuerpo["usuario"]["id"] == candidato.id

    listado = client.get(_url_colaboradores(proyecto.id), headers=headers(admin)).json()
    assert any(c["usuario"]["id"] == candidato.id for c in listado)


def test_agregar_colaborador_dos_veces_devuelve_409(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    candidato = crear_usuario()
    proyecto = crear_proyecto(admin)

    client.post(_url_colaboradores(proyecto.id), json={"usuario_id": candidato.id}, headers=headers(admin))
    resp = client.post(_url_colaboradores(proyecto.id), json={"usuario_id": candidato.id}, headers=headers(admin))
    assert resp.status_code == 409


def test_quitar_y_volver_a_agregar_reactiva(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    candidato = crear_usuario()
    proyecto = crear_proyecto(admin)

    client.post(_url_colaboradores(proyecto.id), json={"usuario_id": candidato.id}, headers=headers(admin))
    quitar = client.delete(f"{_url_colaboradores(proyecto.id)}/{candidato.id}", headers=headers(admin))
    assert quitar.status_code == 204

    listado_tras_quitar = client.get(_url_colaboradores(proyecto.id), headers=headers(admin)).json()
    assert all(c["usuario"]["id"] != candidato.id for c in listado_tras_quitar)

    reactivar = client.post(_url_colaboradores(proyecto.id), json={"usuario_id": candidato.id}, headers=headers(admin))
    assert reactivar.status_code == 201
    assert reactivar.json()["activo"] is True

    listado_final = client.get(_url_colaboradores(proyecto.id), headers=headers(admin)).json()
    assert any(c["usuario"]["id"] == candidato.id for c in listado_final)


def test_quitar_colaborador_es_soft_delete(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers, db_session
):
    from app.models.proyecto_colaborador import ProyectoColaborador

    admin = crear_usuario()
    candidato = crear_usuario()
    proyecto = crear_proyecto(admin)
    fila = agregar_colaborador(proyecto, candidato, activo=True)

    resp = client.delete(f"{_url_colaboradores(proyecto.id)}/{candidato.id}", headers=headers(admin))
    assert resp.status_code == 204

    # La fila sigue en la base, solo cambia `activo`.
    db_session.expire(fila)
    fila_en_bd = db_session.get(ProyectoColaborador, fila.id)
    assert fila_en_bd is not None
    assert fila_en_bd.activo is False


def test_no_se_puede_agregar_a_uno_mismo(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.post(_url_colaboradores(proyecto.id), json={"usuario_id": admin.id}, headers=headers(admin))
    assert resp.status_code == 400


def test_agregar_usuario_inexistente_devuelve_404(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.post(_url_colaboradores(proyecto.id), json={"usuario_id": 999999}, headers=headers(admin))
    assert resp.status_code == 404


def test_colaborador_no_dueno_no_puede_agregar(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers
):
    admin = crear_usuario()
    colaborador = crear_usuario(rol=RolUsuario.COLABORADOR)
    tercero = crear_usuario()
    proyecto = crear_proyecto(admin)
    agregar_colaborador(proyecto, colaborador, activo=True)

    resp = client.post(
        _url_colaboradores(proyecto.id), json={"usuario_id": tercero.id}, headers=headers(colaborador)
    )
    assert resp.status_code == 403


def test_colaborador_no_dueno_no_puede_quitar(
    client, crear_usuario, crear_proyecto, agregar_colaborador, headers
):
    admin = crear_usuario()
    colaborador = crear_usuario(rol=RolUsuario.COLABORADOR)
    proyecto = crear_proyecto(admin)
    agregar_colaborador(proyecto, colaborador, activo=True)

    resp = client.delete(f"{_url_colaboradores(proyecto.id)}/{colaborador.id}", headers=headers(colaborador))
    assert resp.status_code == 403


def test_colaborador_activo_puede_listar(client, crear_usuario, crear_proyecto, agregar_colaborador, headers):
    admin = crear_usuario()
    colaborador = crear_usuario(rol=RolUsuario.COLABORADOR)
    proyecto = crear_proyecto(admin)
    agregar_colaborador(proyecto, colaborador, activo=True)

    resp = client.get(_url_colaboradores(proyecto.id), headers=headers(colaborador))
    assert resp.status_code == 200


def test_usuario_sin_acceso_no_puede_listar(client, crear_usuario, crear_proyecto, headers):
    admin = crear_usuario()
    ajeno = crear_usuario()
    proyecto = crear_proyecto(admin)

    resp = client.get(_url_colaboradores(proyecto.id), headers=headers(ajeno))
    assert resp.status_code == 403
